import gzip

from contig.models import ExecutionTarget, RunRecord, TaskEvent
from contig.runner import _discover_qc
from contig.verification.run_qc import evaluate_run_qc, run_qc
from contig.verification.structural import ExpectedOutputs

GOOD_MQC = (
    '{"report_general_stats_data":[{'
    '"S1":{"uniquely_mapped_percent":92.0,"percent_assigned":85.0,"total_reads":1000000.0},'
    '"S2":{"uniquely_mapped_percent":90.0,"percent_assigned":84.0,"total_reads":1100000.0}}]}'
)
BAD_MQC = '{"report_general_stats_data":[{"S2":{"uniquely_mapped_percent":30.0}}]}'


def test_evaluate_run_qc_passes_good_metrics(tmp_path):
    f = tmp_path / "multiqc_data.json"
    f.write_text(GOOD_MQC)
    results = evaluate_run_qc(f)
    assert results
    assert all(r.status == "pass" for r in results)


def test_evaluate_run_qc_flags_low_alignment(tmp_path):
    f = tmp_path / "multiqc_data.json"
    f.write_text(BAD_MQC)
    results = evaluate_run_qc(f)
    assert any(r.status == "fail" for r in results)


def test_evaluate_run_qc_uses_default_rnaseq_pack(tmp_path):
    f = tmp_path / "multiqc_data.json"
    f.write_text(GOOD_MQC)
    results = evaluate_run_qc(f)
    assert any(r.check.startswith("alignment_rate") for r in results)


TWO_SAMPLE_MQC = (
    '{"report_general_stats_data":[{'
    '"S1":{"uniquely_mapped_percent":90.0,"percent_assigned":85.0,"total_reads":1000000.0},'
    '"S2":{"uniquely_mapped_percent":91.0,"percent_assigned":86.0,"total_reads":1050000.0}}]}'
)


def test_evaluate_run_qc_returns_empty_for_no_metrics(tmp_path):
    # MultiQC present but with no general-stats samples -> no QC ran -> unverified,
    # NOT a spurious min_sample_count fail.
    f = tmp_path / "multiqc_data.json"
    f.write_text('{"report_general_stats_data": []}')
    assert evaluate_run_qc(f) == []


def test_evaluate_run_qc_includes_cross_sample_checks(tmp_path):
    f = tmp_path / "multiqc_data.json"
    f.write_text(TWO_SAMPLE_MQC)
    results = evaluate_run_qc(f)
    checks = [r.check for r in results]
    assert any(c.startswith("min_sample_count") for c in checks)
    assert any(c.startswith("library_size_skew") for c in checks)


def test_run_qc_combines_metric_and_structural_results(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "multiqc_data.json").write_text(GOOD_MQC)
    results_dir = run_dir / "results"
    results_dir.mkdir()
    (results_dir / "sample.bam").write_bytes(b"aligned reads")

    manifest = ExpectedOutputs(required=["*.bam"])
    results = run_qc(run_dir, results_dir=results_dir, manifest=manifest)

    assert any(r.kind == "metric" for r in results)
    assert any(r.kind == "structural" for r in results)
    assert all(r.status == "pass" for r in results)


def test_run_qc_fails_verdict_on_missing_required_output(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "multiqc_data.json").write_text(GOOD_MQC)
    results_dir = run_dir / "results"
    results_dir.mkdir()  # required bam never produced

    manifest = ExpectedOutputs(required=["*.bam"])
    results = run_qc(run_dir, results_dir=results_dir, manifest=manifest)

    record = RunRecord(
        run_id="r",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        qc_results=results,
    )
    assert record.verdict == "fail"


def test_successful_run_with_good_qc_reads_pass(tmp_path):
    # the full loop: a completed run + passing QC attached -> verdict "pass"
    f = tmp_path / "multiqc_data.json"
    f.write_text(GOOD_MQC)
    record = RunRecord(
        run_id="r",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        qc_results=evaluate_run_qc(f),
    )
    assert record.verdict == "pass"


DUP_HIGH_MQC = '{"report_general_stats_data":[{"S1":{"percent_duplication":95.0}}]}'


def test_discover_qc_emits_rnaseq_plausibility_for_rnaseq_assay(tmp_path):
    # An RNA-seq run with a MultiQC report carrying percent_duplication above the
    # warn band (95.0 > 80.0) must emit a duplication_rate:<sample> warn result.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "multiqc_data.json").write_text(DUP_HIGH_MQC)

    results = _discover_qc(run_dir, assay="rnaseq")
    checks = {r.check: r for r in results}
    assert "duplication_rate:S1" in checks
    assert checks["duplication_rate:S1"].status == "warn"


def test_discover_qc_does_not_emit_rnaseq_plausibility_for_non_rnaseq_assay(tmp_path):
    # A non-rnaseq assay (e.g. variant_calling) must NOT get RNA-seq plausibility
    # checks, even when a MultiQC report is present — strict assay gate.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "multiqc_data.json").write_text(DUP_HIGH_MQC)

    results = _discover_qc(run_dir, assay="variant_calling")
    checks = [r.check for r in results]
    assert not any(c.startswith("duplication_rate:") for c in checks)
    assert not any(c.startswith("rrna_contamination:") for c in checks)


_VCF_HEADER = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"
)


def _write_vcf(path, rows):
    """rows: list of (chrom, pos, ref, alt, gt)."""
    body = "".join(
        f"{c}\t{p}\t.\t{r}\t{al}\t.\tPASS\t.\tGT\t{gt}\n" for (c, p, r, al, gt) in rows
    )
    path.write_text(_VCF_HEADER + body)
    return path


def _record_with(qc_results, pipeline="nf-core/sarek", revision="3.5.1"):
    return RunRecord(
        run_id="r",
        pipeline=pipeline,
        pipeline_revision=revision,
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        qc_results=qc_results,
    )


def test_run_qc_includes_concordance_when_vcf_given(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    concordant_rows = [
        ("chr1", 100, "A", "G", "0/1"),
        ("chr1", 200, "C", "T", "1/1"),
    ]
    primary = _write_vcf(tmp_path / "primary.vcf", concordant_rows)

    # A concordant pair: both checks pass -> verdict is pass.
    agree = _write_vcf(tmp_path / "agree.vcf", concordant_rows)
    results = run_qc(
        run_dir, concordance=(primary, agree), assay="variant_calling"
    )
    assert any(r.kind == "concordance" for r in results)
    assert {r.check for r in results if r.kind == "concordance"} == {
        "genotype_concordance",
        "site_overlap",
    }
    assert _record_with(results).verdict in ("pass", "unverified")

    # A divergent pair: concordance can WARN but must never push the verdict to FAIL.
    divergent = _write_vcf(
        tmp_path / "divergent.vcf",
        [("chr9", 999, "G", "A", "0/1")],  # disjoint sites
    )
    div_results = run_qc(
        run_dir, concordance=(primary, divergent), assay="variant_calling"
    )
    assert any(r.kind == "concordance" for r in div_results)
    assert _record_with(div_results).verdict in ("pass", "warn", "unverified")
    assert _record_with(div_results).verdict != "fail"


def _write_count_matrix(path, rows):
    """rows: list of (gene_id, count). Writes a header + one column TSV matrix."""
    body = "gene_id\tsample1\n"
    body += "".join(f"{gene}\t{count}\n" for (gene, count) in rows)
    path.write_text(body)
    return path


def test_run_qc_includes_rnaseq_count_concordance(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    # A concordant pair: >= 10 shared genes with matching counts (not UNVERIFIED).
    base_rows = [(f"gene{i}", (i + 1) * 100) for i in range(12)]
    primary = _write_count_matrix(tmp_path / "primary.tsv", base_rows)
    agree = _write_count_matrix(tmp_path / "agree.tsv", base_rows)

    results = run_qc(run_dir, concordance=(primary, agree), assay="rnaseq")
    assert any(r.check == "spearman_concordance" and r.kind == "concordance" for r in results)
    assert _record_with(results).verdict in ("pass", "unverified")

    # A divergent pair: same genes but a scrambled monotonic-breaking order so the
    # Spearman rho drops below 0.90. Concordance can WARN but never FAIL a verdict.
    scrambled = [500, 100, 1200, 300, 900, 200, 1100, 400, 800, 700, 1000, 600]
    div_rows = [(f"gene{i}", scrambled[i]) for i in range(12)]
    divergent = _write_count_matrix(tmp_path / "divergent.tsv", div_rows)

    div_results = run_qc(run_dir, concordance=(primary, divergent), assay="rnaseq")
    assert any(
        r.check == "spearman_concordance" and r.kind == "concordance"
        for r in div_results
    )
    spearman = next(r for r in div_results if r.check == "spearman_concordance")
    assert spearman.value is not None and spearman.value < 0.90
    assert _record_with(div_results).verdict != "fail"


# Rows with both transitions and transversions plus a het and a hom-alt genotype,
# so both plausibility metrics (ts_tv_ratio, het_hom_ratio) are computable.
_PLAUSIBLE_ROWS = [
    ("chr1", 100, "A", "G", "0/1"),  # transition, het
    ("chr1", 200, "C", "T", "1/1"),  # transition, hom-alt
    ("chr1", 300, "A", "C", "0/1"),  # transversion, het
]


def _write_vcf_gz(path, rows):
    """Write a gzipped VCF (the `*.vcf.gz` the variant_calling manifest globs for)."""
    body = "".join(
        f"{c}\t{p}\t.\t{r}\t{al}\t.\tPASS\t.\tGT\t{gt}\n" for (c, p, r, al, gt) in rows
    )
    path.write_bytes(gzip.compress((_VCF_HEADER + body).encode()))
    return path


def test_discover_qc_includes_plausibility_for_variant_run(tmp_path):
    # A germline run whose results carry a primary VCF and NO multiqc_data.json
    # still gets the plausibility checks: the MultiQC-independent path.
    run_dir = tmp_path / "run"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    _write_vcf_gz(results_dir / "x.vcf.gz", _PLAUSIBLE_ROWS)

    results = _discover_qc(run_dir, assay="variant_calling")
    checks = [r.check for r in results]
    assert any(c.startswith("ts_tv_ratio") for c in checks)
    assert any(c.startswith("het_hom_ratio") for c in checks)


def test_plausibility_not_run_for_non_variant_assay(tmp_path):
    # An rnaseq run does not get the variant plausibility checks, even if a VCF
    # happens to sit under its results.
    run_dir = tmp_path / "run"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    _write_vcf_gz(results_dir / "x.vcf.gz", _PLAUSIBLE_ROWS)

    results = _discover_qc(run_dir, assay="rnaseq")
    checks = [r.check for r in results]
    assert not any(c.startswith("ts_tv_ratio") for c in checks)
    assert not any(c.startswith("het_hom_ratio") for c in checks)


def test_plausibility_runs_alongside_multiqc(tmp_path):
    # A variant run that ALSO has a multiqc_data.json still gets the plausibility
    # checks: they are additive, not gated behind the presence of a MultiQC report.
    run_dir = tmp_path / "run"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    (run_dir / "multiqc_data.json").write_text(GOOD_MQC)
    _write_vcf_gz(results_dir / "x.vcf.gz", _PLAUSIBLE_ROWS)

    results = _discover_qc(run_dir, assay="variant_calling")
    checks = [r.check for r in results]
    assert any(c.startswith("ts_tv_ratio") for c in checks)
    assert any(c.startswith("het_hom_ratio") for c in checks)
