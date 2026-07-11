import gzip

import pytest

from contig.models import ExecutionTarget, RunRecord, TaskEvent, overall_verdict
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


# --- sex_plausibility verdict wiring (germline _discover_qc gate) -----------

# Discordant germline signature: autosomal-level chrX heterozygosity (24 het +
# 6 hom, ratio 0.8 >= X_HET_HIGH) together with 6 chrY variant sites (>=
# Y_PRESENT_FLOOR) -- a real VCF can never carry both, so this warns. Rows are
# added on top of _PLAUSIBLE_ROWS (which drive ts_tv/het_hom) in the SAME VCF,
# since the gate reuses one located `vcfs[0]` for both checks.
_DISCORDANT_SEX_ROWS = (
    _PLAUSIBLE_ROWS
    + [("chrX", 3_000_000 + i, "A", "G", "0/1") for i in range(24)]
    + [("chrX", 4_000_000 + i, "A", "G", "0/0") for i in range(3)]
    + [("chrX", 5_000_000 + i, "A", "G", "1/1") for i in range(3)]
    + [("chrY", 10_000_000 + i, "A", "G", "0/1") for i in range(6)]
)


def test_discover_qc_includes_sex_plausibility_for_variant_run(tmp_path):
    # A germline run whose VCF carries a discordant chrX/chrY signature gets
    # sex_plausibility (WARN) + the informational x_het_ratio, alongside the
    # still-present ts_tv/het_hom checks -- no regression to those.
    run_dir = tmp_path / "run"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    _write_vcf_gz(results_dir / "x.vcf.gz", _DISCORDANT_SEX_ROWS)

    results = _discover_qc(run_dir, assay="variant_calling")
    checks = {r.check: r for r in results}
    sex = next(v for k, v in checks.items() if k.startswith("sex_plausibility:"))
    assert sex.status == "warn"
    assert any(k.startswith("x_het_ratio:") for k in checks)
    assert any(k.startswith("ts_tv_ratio") for k in checks)
    assert any(k.startswith("het_hom_ratio") for k in checks)


def test_sex_plausibility_not_run_for_non_variant_assay(tmp_path):
    # A non-germline assay (e.g. rnaseq) never gets sex_plausibility, even if a
    # discordant-shaped VCF happens to sit under its results -- strict gate.
    run_dir = tmp_path / "run"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    _write_vcf_gz(results_dir / "x.vcf.gz", _DISCORDANT_SEX_ROWS)

    results = _discover_qc(run_dir, assay="rnaseq")
    checks = [r.check for r in results]
    assert not any(c.startswith("sex_plausibility:") for c in checks)
    assert not any(c.startswith("x_het_ratio:") for c in checks)


def test_sex_plausibility_warn_does_not_force_fail_verdict(tmp_path):
    # Verdict-invariance: a WARN sex_plausibility result, on its own, reduces
    # to "warn" -- never "fail" -- confirming (per overall_verdict's fail>warn>
    # pass>unverified precedence and cli.py's exit-decided-by-pipeline-success-
    # only contract) that this check cannot force a run's exit code.
    run_dir = tmp_path / "run"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    _write_vcf_gz(results_dir / "x.vcf.gz", _DISCORDANT_SEX_ROWS)

    results = _discover_qc(run_dir, assay="variant_calling")
    sex_only = [r for r in results if r.check.startswith("sex_plausibility:")]
    assert sex_only and sex_only[0].status == "warn"
    assert overall_verdict(sex_only) == "warn"


# --- Somatic VAF plausibility runner gate (Phase 4) -------------------------

# A two-sample somatic VCF: column order NORMAL then TUMOR (so the gate must
# select the tumor by the ##tumor_sample= header name, not by position). FORMAT
# is GT:AF:AD:DP; plausible tumor AFs (0.30, 0.40) sit inside the WARN band.
_SOMATIC_HEADER = (
    "##fileformat=VCFv4.2\n"
    "##tumor_sample=TUMOR\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tNORMAL\tTUMOR\n"
)
_SOMATIC_ROWS = [
    ("chr1", 100, "A", "G", "0/1:0.30:14,6:20"),
    ("chr1", 200, "C", "T", "0/1:0.40:12,8:20"),
]


def _write_somatic_vcf_gz(path, header=_SOMATIC_HEADER, rows=_SOMATIC_ROWS):
    """Write a gzipped two-sample somatic VCF (NORMAL then TUMOR columns)."""
    body = "".join(
        f"{c}\t{p}\t.\t{r}\t{al}\t.\tPASS\t.\tGT:AF:AD:DP\t0/0:0.0:10,0:10\t{t}\n"
        for (c, p, r, al, t) in rows
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress((header + body).encode()))
    return path


def test_discover_qc_includes_somatic_plausibility(tmp_path):
    # A somatic run whose results carry a Mutect2 VCF (under a mutect2/ path) and
    # NO multiqc_data.json still gets the somatic plausibility checks.
    run_dir = tmp_path / "run"
    vcf = run_dir / "results" / "variant_calling" / "mutect2" / "T_vs_N" / "x.vcf.gz"
    _write_somatic_vcf_gz(vcf)

    results = _discover_qc(run_dir, assay="somatic_variant_calling")
    checks = [r.check for r in results]
    assert any(c.startswith("median_vaf") for c in checks)
    assert any(c.startswith("somatic_variant_count") for c in checks)
    assert any(c.startswith("pon_applied") for c in checks)


def test_somatic_plausibility_not_run_for_non_somatic_assay(tmp_path):
    # The same Mutect2 VCF under a germline (variant_calling) run does NOT get the
    # somatic checks — the gate is strictly keyed to somatic_variant_calling.
    run_dir = tmp_path / "run"
    vcf = run_dir / "results" / "variant_calling" / "mutect2" / "T_vs_N" / "x.vcf.gz"
    _write_somatic_vcf_gz(vcf)

    results = _discover_qc(run_dir, assay="variant_calling")
    checks = [r.check for r in results]
    assert not any(c.startswith("median_vaf") for c in checks)
    assert not any(c.startswith("somatic_variant_count") for c in checks)
    assert not any(c.startswith("pon_applied") for c in checks)


def test_somatic_only_strelka_vcf_is_unverified(tmp_path):
    # VCFs exist but none under a mutect2 path (only Strelka) -> a single
    # UNVERIFIED somatic_vaf_plausibility result (D1), never a silent pass.
    # NB: the test name deliberately avoids the substring "mutect2" — pytest bakes
    # the test name into tmp_path, and the D1 gate matches "mutect2" anywhere in the
    # VCF's absolute path (str(path).lower()), so a "mutect2"-named test would false-
    # positively select this VCF as the Mutect2 candidate.
    run_dir = tmp_path / "run"
    vcf = run_dir / "results" / "variant_calling" / "strelka" / "T_vs_N" / "x.vcf.gz"
    _write_somatic_vcf_gz(vcf)

    results = _discover_qc(run_dir, assay="somatic_variant_calling")
    unverified = [r for r in results if r.check == "somatic_vaf_plausibility"]
    assert len(unverified) == 1
    assert unverified[0].status == "unverified"
    assert unverified[0].value is None
    assert not any(r.check.startswith("median_vaf") for r in results)


def test_somatic_mutect2_in_ancestor_dir_does_not_misselect_strelka(tmp_path):
    # Robustness: "mutect2" appearing in an ANCESTOR directory (a workspace or run-id
    # name outside the run's output tree) must NOT cause a Strelka-only VCF to be read
    # as the Mutect2 candidate. The gate matches "mutect2" as a path component BELOW
    # run_dir, not as a substring of the absolute path — so this stays UNVERIFIED,
    # never a false pass on the wrong caller's data.
    run_dir = tmp_path / "mutect2_workspace" / "run"
    vcf = run_dir / "results" / "variant_calling" / "strelka" / "T_vs_N" / "x.vcf.gz"
    _write_somatic_vcf_gz(vcf)

    results = _discover_qc(run_dir, assay="somatic_variant_calling")
    unverified = [r for r in results if r.check == "somatic_vaf_plausibility"]
    assert len(unverified) == 1
    assert unverified[0].status == "unverified"
    assert not any(r.check.startswith("median_vaf") for r in results)


def test_somatic_no_vcf_at_all_skips_silently(tmp_path):
    # No *.vcf.gz anywhere -> the somatic gate emits nothing and does not crash
    # (structural QC already covers a missing required output).
    run_dir = tmp_path / "run"
    (run_dir / "results").mkdir(parents=True)

    results = _discover_qc(run_dir, assay="somatic_variant_calling")
    checks = [r.check for r in results]
    assert not any(c.startswith("median_vaf") for c in checks)
    assert not any(c.startswith("somatic_variant_count") for c in checks)
    assert not any(c.startswith("pon_applied") for c in checks)
    assert not any(c == "somatic_vaf_plausibility" for c in checks)


# --- Somatic Strelka2-vs-Mutect2 concordance auto-wiring (site-overlap Phase 2) --
#
# Reuses the somatic manifest's globbed *.vcf.gz list, exactly as VAF
# plausibility does; the concordance check is independent and additive.


def _pass_site_rows(n, chrom="chr1", start=100):
    return [(chrom, start + i, "A", "G") for i in range(n)]


def _write_pass_vcf_gz(path, rows):
    """A minimal FILTER-PASS VCF (rows: (chrom, pos, ref, alt)), gzipped, at the
    path sarek writes a somatic caller's VCF under."""
    header = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
    body = "".join(f"{c}\t{p}\t.\t{r}\t{a}\t.\tPASS\t.\n" for (c, p, r, a) in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress((header + body).encode()))
    return path


def test_discover_qc_includes_somatic_concordance_for_both_callers(tmp_path):
    run_dir = tmp_path / "run"
    rows = _pass_site_rows(12)
    _write_pass_vcf_gz(
        run_dir / "results" / "variant_calling" / "mutect2" / "T_vs_N" / "x.vcf.gz", rows
    )
    _write_pass_vcf_gz(
        run_dir
        / "results"
        / "variant_calling"
        / "strelka"
        / "T_vs_N"
        / "T_vs_N.strelka.somatic_snvs.vcf.gz",
        rows[:6],
    )
    _write_pass_vcf_gz(
        run_dir
        / "results"
        / "variant_calling"
        / "strelka"
        / "T_vs_N"
        / "T_vs_N.strelka.somatic_indels.vcf.gz",
        rows[6:],
    )

    results = _discover_qc(run_dir, assay="somatic_variant_calling")

    concordance = [r for r in results if r.kind == "concordance"]
    assert any(r.check == "somatic_site_overlap" for r in concordance)


def test_discover_qc_somatic_concordance_warn_does_not_fail_verdict(tmp_path):
    run_dir = tmp_path / "run"
    m_rows = _pass_site_rows(12, start=100)
    s_rows = _pass_site_rows(12, start=900)  # disjoint -> warn, not fail
    _write_pass_vcf_gz(
        run_dir / "results" / "variant_calling" / "mutect2" / "T_vs_N" / "x.vcf.gz", m_rows
    )
    _write_pass_vcf_gz(
        run_dir
        / "results"
        / "variant_calling"
        / "strelka"
        / "T_vs_N"
        / "T_vs_N.strelka.somatic_snvs.vcf.gz",
        s_rows,
    )

    results = _discover_qc(run_dir, assay="somatic_variant_calling")

    concordance = [r for r in results if r.check == "somatic_site_overlap"]
    assert len(concordance) == 1
    assert concordance[0].status == "warn"
    assert _record_with(results).verdict != "fail"


def test_discover_qc_no_somatic_concordance_for_germline_assay(tmp_path):
    run_dir = tmp_path / "run"
    rows = _pass_site_rows(12)
    _write_pass_vcf_gz(
        run_dir / "results" / "variant_calling" / "mutect2" / "T_vs_N" / "x.vcf.gz", rows
    )
    _write_pass_vcf_gz(
        run_dir
        / "results"
        / "variant_calling"
        / "strelka"
        / "T_vs_N"
        / "T_vs_N.strelka.somatic_snvs.vcf.gz",
        rows,
    )

    results = _discover_qc(run_dir, assay="variant_calling")

    assert not any(r.check == "somatic_site_overlap" for r in results)


def test_discover_qc_no_somatic_concordance_for_rnaseq_assay(tmp_path):
    run_dir = tmp_path / "run"
    rows = _pass_site_rows(12)
    _write_pass_vcf_gz(
        run_dir / "results" / "variant_calling" / "mutect2" / "T_vs_N" / "x.vcf.gz", rows
    )
    _write_pass_vcf_gz(
        run_dir
        / "results"
        / "variant_calling"
        / "strelka"
        / "T_vs_N"
        / "T_vs_N.strelka.somatic_snvs.vcf.gz",
        rows,
    )

    results = _discover_qc(run_dir, assay="rnaseq")

    assert not any(r.check == "somatic_site_overlap" for r in results)


# --------------------------------------------------------------------------- #
# scrnaseq cell-QC ingestion gate (single-cell metric ingestion).
# The base pipeline does not route these metrics into MultiQC, so a dedicated
# gate parses the aligner's cell-QC file and drives SCRNASEQ_RULE_PACK.
# --------------------------------------------------------------------------- #

_STARSOLO_HEALTHY = (
    "Estimated Number of Cells,5000\n"
    "Median Gene per Cell,1800\n"
    "Fraction of Unique Reads in Cells,0.85\n"
)
_STARSOLO_NEAR_EMPTY = (
    "Estimated Number of Cells,50\n"
    "Median Gene per Cell,1800\n"
    "Fraction of Unique Reads in Cells,0.85\n"
)
_CELLRANGER_HEALTHY = (
    '"Estimated Number of Cells","Median Genes per Cell","Fraction Reads in Cells"\n'
    '"6,000","2,000","91.0%"\n'
)


def _write_starsolo(run_dir, sample, text):
    p = run_dir / "star" / sample / f"{sample}.Solo.out" / "Gene" / "Summary.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def _write_cellranger(run_dir, sample, text):
    p = run_dir / "cellranger" / "count" / sample / "outs" / "metrics_summary.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_discover_qc_starsolo_healthy_passes(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_starsolo(run_dir, "S1", _STARSOLO_HEALTHY)

    results = _discover_qc(run_dir, assay="scrnaseq")
    checks = {r.check: r for r in results}
    assert "estimated_cells:S1" in checks
    assert checks["estimated_cells:S1"].status == "pass"
    assert checks["estimated_cells:S1"].value == 5000.0


def test_discover_qc_starsolo_near_empty_fails(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_starsolo(run_dir, "S1", _STARSOLO_NEAR_EMPTY)

    results = _discover_qc(run_dir, assay="scrnaseq")
    checks = {r.check: r for r in results}
    assert checks["estimated_cells:S1"].status == "fail"


def test_discover_qc_cellranger_fraction_normalized(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_cellranger(run_dir, "S1", _CELLRANGER_HEALTHY)

    results = _discover_qc(run_dir, assay="scrnaseq")
    checks = {r.check: r for r in results}
    # 91.0% -> 0.91 (a fraction) so it clears the 0.7 warn band -> pass, not a
    # spurious warn from comparing 91.0 to 0.7.
    assert checks["fraction_reads_in_cells:S1"].status == "pass"
    assert checks["fraction_reads_in_cells:S1"].value == pytest.approx(0.91)


def test_discover_qc_scrnaseq_empty_file_is_unverified(tmp_path):
    # A cell-QC file present but carrying no mappable metric -> explicit UNVERIFIED
    # for that sample, never a silent no-op and never a pass.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_starsolo(run_dir, "S1", "Number of Reads,1000000\n")  # nothing mappable

    results = _discover_qc(run_dir, assay="scrnaseq")
    statuses = {r.status for r in results if r.check.endswith(":S1") or "S1" in r.check}
    assert results, "expected an explicit unverified, not an empty list"
    assert all(r.status != "pass" for r in results)
    assert any(r.status == "unverified" for r in results)


def test_discover_qc_scrnaseq_no_file_skips_silently(tmp_path):
    # No cell-QC artifact at all (e.g. simpleaf HTML-only) -> the gate adds nothing;
    # structural QC covers a missing required output. Mirrors the germline no-VCF path.
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    results = _discover_qc(run_dir, assay="scrnaseq")
    assert not any(r.check.startswith("estimated_cells:") for r in results)
    assert not any(r.check.startswith("scrnaseq_cell_qc:") for r in results)


def test_discover_qc_scrnaseq_prefers_cellranger_over_starsolo(tmp_path):
    # Both aligners' outputs for the same sample -> deterministic Cell Ranger
    # preference, no merge: exactly one estimated_cells:S1 with the CR value.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_starsolo(run_dir, "S1", _STARSOLO_HEALTHY)          # estimated_cells 5000
    _write_cellranger(run_dir, "S1", _CELLRANGER_HEALTHY)      # estimated_cells 6000

    results = _discover_qc(run_dir, assay="scrnaseq")
    est = [r for r in results if r.check == "estimated_cells:S1"]
    assert len(est) == 1
    assert est[0].value == 6000.0  # Cell Ranger won


def test_discover_qc_scrnaseq_gate_not_applied_to_other_assays(tmp_path):
    # A Summary.csv present but the assay is rnaseq/variant_calling -> the scrnaseq
    # gate must not fire (strict assay gate).
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_starsolo(run_dir, "S1", _STARSOLO_HEALTHY)

    for assay in ("rnaseq", "variant_calling"):
        results = _discover_qc(run_dir, assay=assay)
        assert not any(r.check.startswith("estimated_cells:") for r in results)


# --------------------------------------------------------------------------- #
# methylseq bisulfite QC ingestion gate (methylseq-firing aspect of
# assay-qc-verdict-fires). nf-core/methylseq does not reliably route Bismark's
# per-sample metrics into MultiQC general-stats under a stable slug, so a
# dedicated gate parses Bismark's own on-disk report artifacts and drives
# METHYLSEQ_RULE_PACK. Mirrors the scrnaseq gate above.
# --------------------------------------------------------------------------- #

_BISMARK_ALIGNMENT_HEALTHY = (
    "Bismark report for: S1_R1.fastq.gz and S1_R2.fastq.gz (version: v0.24.1)\n\n"
    "Final Alignment report\n"
    "=======================\n"
    "Sequence pairs analysed in total:\t1000000\n"
    "Mapping efficiency:\t78.90%\n"
)
_BISMARK_ALIGNMENT_FAILED = (
    "Bismark report for: S1_R1.fastq.gz and S1_R2.fastq.gz (version: v0.24.1)\n\n"
    "Final Alignment report\n"
    "=======================\n"
    "Sequence pairs analysed in total:\t1000000\n"
    "Mapping efficiency:\t12.00%\n"
)
_BISMARK_DEDUP_HEALTHY = (
    "Total number of alignments analysed in S1_bismark_bt2_pe.bam:\t789000\n"
    "Total number duplicated alignments removed:\t97335 (12.34%)\n"
)
_BISMARK_SPLITTING_NO_CONTROL = (
    "Bismark methylation extractor report for S1_bismark_bt2_pe.bam\n\n"
    "C methylated in CpG context:\t12.0%\n"
)
_BISMARK_SPLITTING_WITH_CONTROL = (
    "Bismark methylation extractor report for S1_bismark_bt2_pe.bam\n\n"
    "Bisulfite conversion rate:\t99.30%\n"
)


def _write_bismark_alignment(run_dir, sample, text, paired=True):
    suffix = "PE" if paired else "SE"
    p = run_dir / "bismark" / "reports" / f"{sample}_bismark_bt2_{suffix}_report.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def _write_bismark_dedup(run_dir, sample, text):
    p = (
        run_dir
        / "bismark"
        / "deduplicated"
        / f"{sample}_bismark_bt2_pe.deduplication_report.txt"
    )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def _write_bismark_splitting(run_dir, sample, text):
    p = run_dir / "bismark" / "methylation_calls" / f"{sample}_splitting_report.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_discover_qc_methylseq_healthy_alignment_and_dedup_pass(tmp_path):
    # A1: healthy alignment+dedup -> non-UNVERIFIED mapping_efficiency:<s> +
    # duplication_rate:<s>.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_bismark_alignment(run_dir, "S1", _BISMARK_ALIGNMENT_HEALTHY)
    _write_bismark_dedup(run_dir, "S1", _BISMARK_DEDUP_HEALTHY)

    results = _discover_qc(run_dir, assay="methylseq")
    checks = {r.check: r for r in results}

    assert "mapping_efficiency:S1" in checks
    assert checks["mapping_efficiency:S1"].status != "unverified"
    assert checks["mapping_efficiency:S1"].value == 78.9
    assert "duplication_rate:S1" in checks
    assert checks["duplication_rate:S1"].status != "unverified"
    assert checks["duplication_rate:S1"].value == 12.34


def test_discover_qc_methylseq_low_mapping_efficiency_fails(tmp_path):
    # A2: mapping efficiency < fail_below (30.0) -> FAIL mapping_efficiency:<s>.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_bismark_alignment(run_dir, "S1", _BISMARK_ALIGNMENT_FAILED)

    results = _discover_qc(run_dir, assay="methylseq")
    checks = {r.check: r for r in results}

    assert checks["mapping_efficiency:S1"].status == "fail"


def test_discover_qc_methylseq_zero_usable_metrics_is_unverified(tmp_path):
    # A3a: report present but zero usable metrics -> exactly one
    # methylseq_qc:<sample> UNVERIFIED.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_bismark_alignment(
        run_dir, "S1", "Bismark report for: S1 (version: v0.24.1)\n"  # no mapping line
    )

    results = _discover_qc(run_dir, assay="methylseq")

    unverified = [r for r in results if r.check == "methylseq_qc:S1"]
    assert len(unverified) == 1
    assert unverified[0].status == "unverified"
    assert unverified[0].value is None
    assert unverified[0].kind == "metric"


def test_discover_qc_methylseq_no_artifact_skips_silently(tmp_path):
    # A3b: no methylseq artifact at all -> no methylseq metric result, no crash.
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    results = _discover_qc(run_dir, assay="methylseq")

    assert not any(r.check.startswith("mapping_efficiency:") for r in results)
    assert not any(r.check.startswith("methylseq_qc:") for r in results)


def test_discover_qc_methylseq_alignment_only_sample_no_unverified(tmp_path):
    # A4: alignment-only sample (no dedup, no conversion) -> PASS/WARN on mapping
    # efficiency and no methylseq_qc:<s> UNVERIFIED.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_bismark_alignment(run_dir, "S1", _BISMARK_ALIGNMENT_HEALTHY)

    results = _discover_qc(run_dir, assay="methylseq")
    checks = {r.check: r for r in results}

    assert checks["mapping_efficiency:S1"].status in {"pass", "warn"}
    assert not any(r.check == "methylseq_qc:S1" for r in results)
    assert not any(r.check.startswith("duplication_rate:") for r in results)


def test_discover_qc_methylseq_conversion_only_with_control_line(tmp_path):
    # A5: percent_bs_conversion emitted only with a control line; a standard
    # splitting report omits it (no bisulfite_conversion:<s> result), and the
    # sample still evaluates the rest of its metrics.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_bismark_alignment(run_dir, "S1", _BISMARK_ALIGNMENT_HEALTHY)
    _write_bismark_splitting(run_dir, "S1", _BISMARK_SPLITTING_NO_CONTROL)

    results = _discover_qc(run_dir, assay="methylseq")
    checks = {r.check: r for r in results}

    assert "bisulfite_conversion:S1" not in checks
    assert "mapping_efficiency:S1" in checks
    assert not any(r.check == "methylseq_qc:S1" for r in results)


def test_discover_qc_methylseq_conversion_with_control_line_fires(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_bismark_alignment(run_dir, "S1", _BISMARK_ALIGNMENT_HEALTHY)
    _write_bismark_splitting(run_dir, "S1", _BISMARK_SPLITTING_WITH_CONTROL)

    results = _discover_qc(run_dir, assay="methylseq")
    checks = {r.check: r for r in results}

    assert "bisulfite_conversion:S1" in checks
    assert checks["bisulfite_conversion:S1"].value == 99.3
    assert checks["bisulfite_conversion:S1"].status != "unverified"


def test_discover_qc_methylseq_no_double_emit_with_multiqc(tmp_path):
    # A6: a methylseq run whose MultiQC carries a matching slug does NOT
    # double-emit; the dedicated gate is the single source (M6).
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_bismark_alignment(run_dir, "S1", _BISMARK_ALIGNMENT_HEALTHY)
    mqc = run_dir / "multiqc_data.json"
    mqc.write_text('{"report_general_stats_data":[{"S1":{"percent_aligned":78.9}}]}')

    results = _discover_qc(run_dir, assay="methylseq")

    mapping = [r for r in results if r.check == "mapping_efficiency:S1"]
    assert len(mapping) == 1


def test_discover_qc_methylseq_gate_not_applied_to_other_assays(tmp_path):
    # A7: the methylseq gate is not applied to any other assay.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_bismark_alignment(run_dir, "S1", _BISMARK_ALIGNMENT_HEALTHY)

    results = _discover_qc(run_dir, assay="rnaseq")

    assert not any(r.check.startswith("mapping_efficiency:") for r in results)
    assert not any(r.check.startswith("methylseq_qc:") for r in results)


# --------------------------------------------------------------------------- #
# ampliseq DADA2 QC ingestion gate (ampliseq-firing aspect of
# assay-qc-verdict-fires). nf-core/ampliseq does not reliably route DADA2's
# per-sample metrics into MultiQC general-stats under a stable slug, so a
# dedicated gate parses DADA2's own on-disk stats artifacts and drives
# AMPLISEQ_RULE_PACK. Mirrors the methylseq gate above; the one structural
# difference is that DADA2's artifacts are MULTI-sample files (one file, many
# samples), not one file per sample.
# --------------------------------------------------------------------------- #

_OVERALL_SUMMARY_HEALTHY = (
    "sample\tinput\tfiltered\tdenoisedF\tdenoisedR\tmerged\ttabled\tnonchim\n"
    "S1\t100000\t95000\t94000\t94000\t92000\t92000\t90000\n"
    "S2\t50000\t48000\t47500\t47500\t46000\t46000\t45000\n"
)
_OVERALL_SUMMARY_FAILED = (
    "sample\tinput\tfiltered\tdenoisedF\tdenoisedR\tmerged\ttabled\tnonchim\n"
    "S1\t500\t480\t470\t470\t460\t460\t50\n"
)
_ASV_TABLE_HEALTHY = (
    "ASV_ID\tS1\tS2\tsequence\n"
    "ASV1\t120\t0\tACGT\n"
    "ASV2\t45\t80\tTTAA\n"
    "ASV3\t0\t30\tGGCC\n"
)


def _write_ampliseq_overall_summary(run_dir, text):
    p = run_dir / "dada2" / "dada_stats" / "overall_summary.tsv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def _write_ampliseq_asv_table(run_dir, text):
    p = run_dir / "dada2" / "ASV_table.tsv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_discover_qc_ampliseq_healthy_summary_and_asv_table_pass(tmp_path):
    # B1: healthy overall_summary.tsv + ASV table -> non-UNVERIFIED
    # dada2_read_retention:<s>, asv_count:<s>, sample_read_depth:<s>.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_ampliseq_overall_summary(run_dir, _OVERALL_SUMMARY_HEALTHY)
    _write_ampliseq_asv_table(run_dir, _ASV_TABLE_HEALTHY)

    results = _discover_qc(run_dir, assay="ampliseq")
    checks = {r.check: r for r in results}

    assert "dada2_read_retention:S1" in checks
    assert checks["dada2_read_retention:S1"].status != "unverified"
    assert checks["dada2_read_retention:S1"].value == 90.0
    assert "asv_count:S1" in checks
    assert checks["asv_count:S1"].status != "unverified"
    assert checks["asv_count:S1"].value == 2.0
    assert "sample_read_depth:S1" in checks
    assert checks["sample_read_depth:S1"].status != "unverified"
    assert checks["sample_read_depth:S1"].value == 100000.0


def test_discover_qc_ampliseq_grossly_failed_sample_fails(tmp_path):
    # B2: retention below fail_below (20.0) and reads below fail_below (1000)
    # -> FAIL on both checks.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_ampliseq_overall_summary(run_dir, _OVERALL_SUMMARY_FAILED)

    results = _discover_qc(run_dir, assay="ampliseq")
    checks = {r.check: r for r in results}

    assert checks["dada2_read_retention:S1"].status == "fail"
    assert checks["sample_read_depth:S1"].status == "fail"


def test_discover_qc_ampliseq_zero_usable_metrics_is_unverified(tmp_path):
    # B3: artifact present but zero usable metrics -> exactly one
    # ampliseq_qc:<sample> UNVERIFIED.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_ampliseq_overall_summary(
        run_dir, "sample\tinput\nS1\tN/A\n"  # non-numeric input -> nothing usable
    )

    results = _discover_qc(run_dir, assay="ampliseq")

    unverified = [r for r in results if r.check == "ampliseq_qc:S1"]
    assert len(unverified) == 1
    assert unverified[0].status == "unverified"
    assert unverified[0].value is None
    assert unverified[0].kind == "metric"


def test_discover_qc_ampliseq_no_artifact_skips_silently(tmp_path):
    # B3: no ampliseq artifact at all -> no ampliseq metric result, no crash.
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    results = _discover_qc(run_dir, assay="ampliseq")

    assert not any(r.check.startswith("dada2_read_retention:") for r in results)
    assert not any(r.check.startswith("ampliseq_qc:") for r in results)


def test_discover_qc_ampliseq_partial_summary_only_no_unverified(tmp_path):
    # B4: only overall_summary.tsv present (no ASV table) -> retention +
    # read-depth evaluate; asv_count simply absent; no whole-sample
    # ampliseq_qc:<s> UNVERIFIED.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_ampliseq_overall_summary(run_dir, _OVERALL_SUMMARY_HEALTHY)

    results = _discover_qc(run_dir, assay="ampliseq")
    checks = {r.check: r for r in results}

    assert "dada2_read_retention:S1" in checks
    assert "sample_read_depth:S1" in checks
    assert "asv_count:S1" not in checks
    assert not any(r.check == "ampliseq_qc:S1" for r in results)


def test_discover_qc_ampliseq_multi_sample_no_cross_sample_bleed(tmp_path):
    # B5: multi-sample file -> each sample keyed separately, no cross-sample
    # bleed.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_ampliseq_overall_summary(run_dir, _OVERALL_SUMMARY_HEALTHY)
    _write_ampliseq_asv_table(run_dir, _ASV_TABLE_HEALTHY)

    results = _discover_qc(run_dir, assay="ampliseq")
    checks = {r.check: r for r in results}

    assert checks["dada2_read_retention:S1"].value == 90.0
    assert checks["dada2_read_retention:S2"].value == 90.0
    assert checks["sample_read_depth:S1"].value == 100000.0
    assert checks["sample_read_depth:S2"].value == 50000.0
    assert checks["asv_count:S1"].value == 2.0
    assert checks["asv_count:S2"].value == 2.0


def test_discover_qc_ampliseq_no_double_emit_with_multiqc(tmp_path):
    # B6: an ampliseq run whose MultiQC carries a matching slug does NOT
    # double-emit; the dedicated gate is the single source (M6).
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_ampliseq_overall_summary(run_dir, _OVERALL_SUMMARY_HEALTHY)
    _write_ampliseq_asv_table(run_dir, _ASV_TABLE_HEALTHY)
    mqc = run_dir / "multiqc_data.json"
    mqc.write_text('{"report_general_stats_data":[{"S1":{"percent_retained":90.0}}]}')

    results = _discover_qc(run_dir, assay="ampliseq")

    retention = [r for r in results if r.check == "dada2_read_retention:S1"]
    assert len(retention) == 1


def test_discover_qc_ampliseq_gate_not_applied_to_other_assays(tmp_path):
    # B7: the ampliseq gate is not applied to any other assay.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_ampliseq_overall_summary(run_dir, _OVERALL_SUMMARY_HEALTHY)
    _write_ampliseq_asv_table(run_dir, _ASV_TABLE_HEALTHY)

    results = _discover_qc(run_dir, assay="rnaseq")

    assert not any(r.check.startswith("dada2_read_retention:") for r in results)
    assert not any(r.check.startswith("ampliseq_qc:") for r in results)


# --------------------------------------------------------------------------- #
# mag QUAST + CheckM QC ingestion gate (mag-firing aspect of
# assay-qc-verdict-fires). nf-core/mag does not reliably route QUAST's/
# CheckM's per-bin metrics into MultiQC general-stats under a stable slug, so
# a dedicated gate parses QUAST's and CheckM's own on-disk stats artifacts and
# drives MAG_RULE_PACK. Mirrors the ampliseq gate above; the entity key is the
# BIN (not the sample), matching the pack's own test fixture.
# --------------------------------------------------------------------------- #

_TRANSPOSED_REPORT_HEALTHY = (
    "Assembly\t# contigs\tLargest contig\tTotal length\tN50\tL50\n"
    "bin.1\t42\t120000\t3500000\t8500\t12\n"
    "bin.2\t18\t95000\t2100000\t6200\t8\n"
)
_TRANSPOSED_REPORT_FAILED = (
    "Assembly\t# contigs\tLargest contig\tTotal length\tN50\tL50\n"
    "bin.1\t900\t1200\t50000\t300\t400\n"
)
_CHECKM_SUMMARY_HEALTHY = (
    "Bin Id\tMarker lineage\t# genomes\t# markers\tCompleteness\tContamination\n"
    "bin.1\tk__Bacteria\t100\t120\t95.2\t1.3\n"
    "bin.2\tk__Bacteria\t100\t120\t88.0\t2.1\n"
)


def _write_mag_transposed_report(run_dir, text):
    p = run_dir / "QUAST" / "transposed_report.tsv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def _write_mag_checkm_summary(run_dir, text):
    p = run_dir / "CheckM" / "checkm_summary.tsv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_discover_qc_mag_healthy_quast_and_checkm_pass(tmp_path):
    # C1: healthy QUAST + CheckM -> non-UNVERIFIED assembly_n50:<bin>,
    # bin_completeness:<bin>, bin_contamination:<bin>.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_mag_transposed_report(run_dir, _TRANSPOSED_REPORT_HEALTHY)
    _write_mag_checkm_summary(run_dir, _CHECKM_SUMMARY_HEALTHY)

    results = _discover_qc(run_dir, assay="mag")
    checks = {r.check: r for r in results}

    assert "assembly_n50:bin.1" in checks
    assert checks["assembly_n50:bin.1"].status != "unverified"
    assert checks["assembly_n50:bin.1"].value == 8500.0
    assert "bin_completeness:bin.1" in checks
    assert checks["bin_completeness:bin.1"].status != "unverified"
    assert checks["bin_completeness:bin.1"].value == 95.2
    assert "bin_contamination:bin.1" in checks
    assert checks["bin_contamination:bin.1"].status != "unverified"
    assert checks["bin_contamination:bin.1"].value == 1.3


def test_discover_qc_mag_grossly_failed_bin_fails(tmp_path):
    # C2: N50 below fail_below (1000) -> FAIL.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_mag_transposed_report(run_dir, _TRANSPOSED_REPORT_FAILED)

    results = _discover_qc(run_dir, assay="mag")
    checks = {r.check: r for r in results}

    assert checks["assembly_n50:bin.1"].status == "fail"


def test_discover_qc_mag_zero_usable_metrics_is_unverified(tmp_path):
    # C3: artifact present but zero usable metrics -> exactly one
    # mag_qc:<bin> UNVERIFIED.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_mag_transposed_report(
        run_dir, "Assembly\tN50\nbin.1\tN/A\n"  # non-numeric N50 -> nothing usable
    )

    results = _discover_qc(run_dir, assay="mag")

    unverified = [r for r in results if r.check == "mag_qc:bin.1"]
    assert len(unverified) == 1
    assert unverified[0].status == "unverified"
    assert unverified[0].value is None
    assert unverified[0].kind == "metric"


def test_discover_qc_mag_no_artifact_skips_silently(tmp_path):
    # C3: no mag artifact at all -> no mag metric result, no crash.
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    results = _discover_qc(run_dir, assay="mag")

    assert not any(r.check.startswith("assembly_n50:") for r in results)
    assert not any(r.check.startswith("mag_qc:") for r in results)


def test_discover_qc_mag_partial_quast_only_no_unverified(tmp_path):
    # C4: only QUAST present (no CheckM) -> assembly_n50 evaluates;
    # completeness/contamination simply absent; no whole-bin mag_qc:<bin>
    # UNVERIFIED.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_mag_transposed_report(run_dir, _TRANSPOSED_REPORT_HEALTHY)

    results = _discover_qc(run_dir, assay="mag")
    checks = {r.check: r for r in results}

    assert "assembly_n50:bin.1" in checks
    assert "bin_completeness:bin.1" not in checks
    assert "bin_contamination:bin.1" not in checks
    assert not any(r.check == "mag_qc:bin.1" for r in results)


def test_discover_qc_mag_multi_bin_no_cross_bin_bleed(tmp_path):
    # C5: multi-bin files -> each bin keyed separately, no cross-bin bleed.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_mag_transposed_report(run_dir, _TRANSPOSED_REPORT_HEALTHY)
    _write_mag_checkm_summary(run_dir, _CHECKM_SUMMARY_HEALTHY)

    results = _discover_qc(run_dir, assay="mag")
    checks = {r.check: r for r in results}

    assert checks["assembly_n50:bin.1"].value == 8500.0
    assert checks["assembly_n50:bin.2"].value == 6200.0
    assert checks["bin_completeness:bin.1"].value == 95.2
    assert checks["bin_completeness:bin.2"].value == 88.0
    assert checks["bin_contamination:bin.1"].value == 1.3
    assert checks["bin_contamination:bin.2"].value == 2.1


def test_discover_qc_mag_no_double_emit_with_multiqc(tmp_path):
    # C6: a mag run whose MultiQC carries a matching slug does NOT
    # double-emit; the dedicated gate is the single source (M6).
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_mag_transposed_report(run_dir, _TRANSPOSED_REPORT_HEALTHY)
    _write_mag_checkm_summary(run_dir, _CHECKM_SUMMARY_HEALTHY)
    mqc = run_dir / "multiqc_data.json"
    mqc.write_text('{"report_general_stats_data":[{"bin.1":{"n50":8500.0}}]}')

    results = _discover_qc(run_dir, assay="mag")

    n50 = [r for r in results if r.check == "assembly_n50:bin.1"]
    assert len(n50) == 1


def test_discover_qc_mag_gate_not_applied_to_other_assays(tmp_path):
    # C7: the mag gate is not applied to any other assay.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_mag_transposed_report(run_dir, _TRANSPOSED_REPORT_HEALTHY)
    _write_mag_checkm_summary(run_dir, _CHECKM_SUMMARY_HEALTHY)

    results = _discover_qc(run_dir, assay="rnaseq")

    assert not any(r.check.startswith("assembly_n50:") for r in results)


# --------------------------------------------------------------------------- #
# RNA-seq read-composition QC ingestion gate (rnaseq-mapping-composition-
# plausibility, composition-checks aspect). RSeQC's read_distribution
# exonic/intronic/unassigned fractions do NOT reach MultiQC general-stats, so
# a dedicated gate parses the artifact directly and drives
# RNASEQ_COMPOSITION_PACK. Additive to the existing MultiQC-driven rnaseq
# plausibility gate; the two stay as separate blocks in _discover_qc.
# --------------------------------------------------------------------------- #

_READ_DISTRIBUTION_HEALTHY = """\
Total Reads                   142111
Total Tags                    146154
Total Assigned Tags           129802
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           146030              129779              888.71
5'UTR_Exons         0                   0                   0.00
3'UTR_Exons         0                   0                   0.00
Introns             530                 23                  43.31
TSS_up_1kb          43552               0                   0.00
TSS_up_5kb          76907               0                   0.00
TSS_up_10kb         89031               0                   0.00
TES_down_1kb        40737               0                   0.00
TES_down_5kb        81271               0                   0.00
TES_down_10kb       97060               0                   0.00
=====================================================================
"""

# Different tag counts from the healthy fixture, so a test can assert which
# copy (results/ vs work/) was actually read by the AC6 dedup logic.
_READ_DISTRIBUTION_WORK_COPY = """\
Total Reads                   999999
Total Tags                    999999
Total Assigned Tags           500000
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           1000                100000              100.00
5'UTR_Exons         0                   0                   0.00
3'UTR_Exons         0                   0                   0.00
Introns             1000                400000              400.00
TSS_up_1kb          0                   0                   0.00
TSS_up_5kb          0                   0                   0.00
TSS_up_10kb         0                   0                   0.00
TES_down_1kb        0                   0                   0.00
TES_down_5kb        0                   0                   0.00
TES_down_10kb       0                   0                   0.00
=====================================================================
"""


def _write_read_distribution(run_dir, relative_dir, sample, text):
    d = run_dir / relative_dir
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{sample}.read_distribution.txt"
    f.write_text(text)
    return f


def test_discover_qc_emits_rnaseq_composition_for_rnaseq_assay(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_read_distribution(
        run_dir,
        "results/star_salmon/rseqc/read_distribution",
        "WT_REP1",
        _READ_DISTRIBUTION_HEALTHY,
    )

    results = _discover_qc(run_dir, assay="rnaseq")
    checks = {r.check: r for r in results}

    assert checks["exonic_fraction:WT_REP1"].status == "pass"
    assert checks["intronic_fraction:WT_REP1"].status == "pass"
    assert checks["unassigned_fraction:WT_REP1"].status == "pass"


def test_discover_qc_rnaseq_composition_not_applied_to_other_assays(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_read_distribution(
        run_dir,
        "results/star_salmon/rseqc/read_distribution",
        "WT_REP1",
        _READ_DISTRIBUTION_HEALTHY,
    )

    results = _discover_qc(run_dir, assay="variant_calling")
    checks = [r.check for r in results]

    assert not any(c.startswith("exonic_fraction:") for c in checks)
    assert not any(c.startswith("intronic_fraction:") for c in checks)
    assert not any(c.startswith("unassigned_fraction:") for c in checks)
    assert not any(c.startswith("rnaseq_composition_qc:") for c in checks)


def test_discover_qc_rnaseq_composition_unparseable_is_unverified(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_read_distribution(
        run_dir,
        "results/star_salmon/rseqc/read_distribution",
        "WT_REP1",
        "garbage, not a real RSeQC report\nno usable fields here\n",
    )

    results = _discover_qc(run_dir, assay="rnaseq")
    composition_checks = [r for r in results if r.check == "rnaseq_composition_qc:WT_REP1"]

    assert len(composition_checks) == 1
    assert composition_checks[0].status == "unverified"
    assert composition_checks[0].value is None


def test_discover_qc_rnaseq_composition_no_file_skips_silently(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    results = _discover_qc(run_dir, assay="rnaseq")
    checks = [r.check for r in results]

    assert not any(c.startswith("exonic_fraction:") for c in checks)
    assert not any(c.startswith("intronic_fraction:") for c in checks)
    assert not any(c.startswith("unassigned_fraction:") for c in checks)
    assert not any(c.startswith("rnaseq_composition_qc:") for c in checks)


def test_discover_qc_rnaseq_composition_prefers_results_over_work_copy(tmp_path):
    # AC6 dedup: both a published results/ copy and an intermediate work/ copy
    # exist for the same sample -> exactly one result per check per sample, and
    # the value comes from the results/ copy (not the work/ copy's different
    # tag counts).
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_read_distribution(
        run_dir,
        "results/star_salmon/rseqc/read_distribution",
        "WT_REP1",
        _READ_DISTRIBUTION_HEALTHY,
    )
    _write_read_distribution(
        run_dir,
        "work/ab/cd",
        "WT_REP1",
        _READ_DISTRIBUTION_WORK_COPY,
    )

    results = _discover_qc(run_dir, assay="rnaseq")
    exonic = [r for r in results if r.check == "exonic_fraction:WT_REP1"]

    assert len(exonic) == 1
    # healthy results/ copy -> ~0.9998; work/ copy would give 0.2
    assert exonic[0].value == pytest.approx(129779 / 129802, rel=1e-4)
    assert not any(r.check.startswith("mag_qc:") for r in results)
