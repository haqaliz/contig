"""Phase 1 pins for verify-time concordance capture (PRD R4a, verify-time slice).

The three verify-time concordance evaluators (`evaluate_concordance`,
`evaluate_count_concordance`, `evaluate_sc_count_concordance`) gain the
`somatic_concordance.py:120-149` precedent: an additive `capture_metrics=`
out-param surfacing RAW pre-band `{"value", "n_shared"}` under the run-level
sample key `"S1"`, populated on the normal, too-few/low-n, and
rho-uncomputable paths, so the Phase 2 verify-time corpus hook can store
self-describing cases. An uncomputable metric OMITS "value" (only "n_shared"
is captured, the v0.53.0 precedent) so the guard re-derives the same
UNVERIFIED the module emitted. Absent the param, results are byte-identical
(additive, back-compat).

Status-consistency contract pinned here (mirroring
test_verify_capture_roundtrip.py:269-341): for every captured path, the guard's
re-derivation (`_concordance_status`, verify_corpus.py:166-187) of the stored
{"value", "n_shared"} equals the module's own reduced status for the same
inputs -- the load-bearing pin of the whole feature.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import write_bundle
from contig.cli import app
from contig.models import ExecutionTarget, RunRecord, TaskEvent, VerificationCase
from contig.verify_corpus import _worst_status, evaluate_verify_case
from contig.verification.concordance import (
    concordance_results as genotype_results,
    evaluate_concordance,
)
from contig.verification.count_concordance import (
    concordance_results as count_results,
    evaluate_count_concordance,
)
from contig.verification.sc_count_concordance import evaluate_sc_count_concordance

# --- guard-side harness (roundtrip-file precedent) -----------------------------


def _dump(results) -> list[dict]:
    """The results as serialized dicts, for byte-identical comparisons."""
    return [r.model_dump() for r in results]


def _predicted(family: str, family_inputs: dict, assay: str = "variant_calling") -> str:
    """The status `evaluate_verify_case` re-derives for ONE family from the
    captured pre-band inputs (spec AC5: values, never stored statuses)."""
    case = VerificationCase(
        case_id="pin",
        description="status-consistency pin (synthetic)",
        source="synthetic",
        assay=assay,
        inputs={family: family_inputs},
    )
    return evaluate_verify_case(case).families[family]


def _module_worst(results) -> str:
    """The family-level status the module evaluator emitted for the same metric
    values, reduced exactly the way the guard reduces (worst non-informational)."""
    return _worst_status(r.status for r in results if not r.informational)


# --- germline fixtures (tests/verification/test_concordance.py precedent) ------


def _vcf_line(chrom, pos, ref, alt, gt):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\tGT\t{gt}\n"


def _write_vcf(path, rows):
    """rows: list of (chrom, pos, ref, alt, gt)."""
    header = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "".join(_vcf_line(*r) for r in rows))
    return path


# --- counts fixtures (tests/verification/test_count_concordance.py precedent) ---


def _write_counts(path, mapping):
    """mapping: {gene_id: scalar count} -> a one-sample-column TSV, no header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{gene}\t{value}\n" for gene, value in mapping.items()))
    return path


# --- single-cell fixtures (tests/verification/test_sc_count_concordance.py) ----


def _write_triplet(d, genes, cells, counts, *, gene_axis="rows"):
    """A 10x-style triplet (matrix.mtx, features.tsv, barcodes.tsv); counts are
    1-based (gene_index, cell_index, value) with genes as rows by default."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "features.tsv").write_text(
        "".join(
            ("\t".join(g) if isinstance(g, tuple) else str(g)) + "\n" for g in genes
        )
    )
    (d / "barcodes.tsv").write_text("".join(c + "\n" for c in cells))
    nrows, ncols = (len(genes), len(cells)) if gene_axis == "rows" else (len(cells), len(genes))
    lines = [
        "%%MatrixMarket matrix coordinate integer general",
        f"{nrows} {ncols} {len(counts)}",
    ]
    for gi, ci, val in counts:
        r, c = (gi, ci) if gene_axis == "rows" else (ci, gi)
        lines.append(f"{r} {c} {val}")
    mtx = d / "matrix.mtx"
    mtx.write_text("".join(l + "\n" for l in lines))
    return mtx


def _mtx_pseudobulk(d, mapping, *, gene_axis="rows"):
    """A single-cell triplet whose per-gene pseudobulk equals `mapping`."""
    genes = list(mapping)
    counts = [(i + 1, 1, mapping[g]) for i, g in enumerate(genes)]
    return _write_triplet(d, genes=genes, cells=["cell1"], counts=counts, gene_axis=gene_axis)


def _write_dense_counts(path, mapping):
    """A one-sample-column dense pseudobulk TSV, no header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{g}\t{v}\n" for g, v in mapping.items()))
    return path


# --- genotype: normal + no-known-GT paths ---------------------------------------


def test_genotype_capture_normal_and_no_known_gt(tmp_path):
    # normal: 20 shared sites, 17 agree -> raw rate 17/20 = 0.85 (< the 0.90
    # warn band), captured UNROUNDED with float(shared).
    rows_a = [("chr1", 100 + i, "A", "G", "0/1") for i in range(20)]
    rows_b = [("chr1", 100 + i, "A", "G", "0/1") for i in range(17)] + [
        ("chr1", 117 + i, "A", "G", "1/1") for i in range(3)
    ]
    a = _write_vcf(tmp_path / "a.vcf", rows_a)
    b = _write_vcf(tmp_path / "b.vcf", rows_b)
    capture: dict[str, dict[str, float]] = {}
    results = evaluate_concordance(a, b, assay="variant_calling", capture_metrics=capture)
    assert capture["S1"] == {"value": 17 / 20, "n_shared": 20.0}
    assert _module_worst(results) == "warn"
    assert _predicted("concordance_genotype", capture) == "warn"

    # low-n: shared site keys exist but NO site has a known GT in both (rate is
    # None) -> still captured, n_shared 0.0 (the genotype floor is 1, so the
    # stored case re-derives unverified regardless of the value). The pin here
    # is against the rate check's own status, not the family reduction: the
    # second check (site_overlap) legitimately PASSes and has no corpus
    # counterpart -- `_concordance_status` kind "genotype" re-derives the rate
    # check only (_CONCORDANCE_KIND_THRESHOLDS["genotype"] floor 1).
    no_gt = [("chr1", 100, "A", "G", "."), ("chr1", 200, "C", "T", ".")]
    a2 = _write_vcf(tmp_path / "a2.vcf", no_gt)
    b2 = _write_vcf(tmp_path / "b2.vcf", no_gt)
    capture = {}
    results = evaluate_concordance(a2, b2, assay="variant_calling", capture_metrics=capture)
    assert capture["S1"] == {"value": 0.0, "n_shared": 0.0}
    assert {r.check: r.status for r in results} == {
        "genotype_concordance": "unverified",
        "site_overlap": "pass",
    }
    assert _predicted("concordance_genotype", capture) == "unverified"


def test_genotype_capture_absent_param_byte_identical(tmp_path):
    rows = [("chr1", 100 + i, "A", "G", "0/1") for i in range(20)]
    a = _write_vcf(tmp_path / "a.vcf", rows)
    b = _write_vcf(tmp_path / "b.vcf", rows)

    plain = genotype_results(a, b)
    capture: dict[str, dict[str, float]] = {}
    captured = genotype_results(a, b, capture_metrics=capture)

    assert _dump(captured) == _dump(plain)
    assert capture["S1"] == {"value": 1.0, "n_shared": 20.0}


# --- counts: normal + too-few paths ---------------------------------------------


def test_count_capture_normal_and_few(tmp_path):
    # normal: 12 shared genes, identical counts -> raw rho 1.0.
    mapping = {f"gene{i:02d}": (i + 1) * 100 for i in range(12)}
    a = _write_counts(tmp_path / "a.tsv", mapping)
    b = _write_counts(tmp_path / "b.tsv", dict(mapping))
    capture: dict[str, dict[str, float]] = {}
    results = evaluate_count_concordance(a, b, assay="rnaseq", capture_metrics=capture)
    assert capture["S1"] == {"value": 1.0, "n_shared": 12.0}
    assert _module_worst(results) == "pass"
    assert _predicted("concordance_spearman", capture) == "pass"


    # too-few: 5 shared (< _MIN_SHARED_GENES 10) -> still captured with
    # float(shared); n_shared < 10 re-derives unverified regardless of value.
    few = {f"gene{i:02d}": (i + 1) * 100 for i in range(5)}
    a2 = _write_counts(tmp_path / "a2.tsv", few)
    b2 = _write_counts(tmp_path / "b2.tsv", dict(few))
    capture = {}
    results = evaluate_count_concordance(a2, b2, assay="rnaseq", capture_metrics=capture)
    assert capture["S1"] == {"value": 1.0, "n_shared": 5.0}
    assert _module_worst(results) == "unverified"
    assert _predicted("concordance_spearman", capture) == "unverified"

    # single shared gene: rho is not computable -> "value" is OMITTED (only
    # n_shared captured; the v0.53.0 somatic precedent); n_shared 1.0 < 10
    # re-derives unverified.
    one = {"geneA": 10.0}
    a3 = _write_counts(tmp_path / "a3.tsv", one)
    b3 = _write_counts(tmp_path / "b3.tsv", dict(one))
    capture = {}
    results = evaluate_count_concordance(a3, b3, assay="rnaseq", capture_metrics=capture)
    assert capture["S1"] == {"n_shared": 1.0}
    assert _module_worst(results) == "unverified"
    assert _predicted("concordance_spearman", capture) == "unverified"


def test_count_capture_rho_none_shared_ge_floor(tmp_path):
    # rho UNCOMPUTABLE (all counts constant -> all ranks tied -> zero-variance
    # ranked vectors) while shared >= the 10-gene spearman floor: the module's
    # spearman check is UNVERIFIED, and the capture must OMIT "value" (the
    # v0.53.0 somatic precedent) so the guard re-derives the same UNVERIFIED --
    # a 0.0 placeholder with n_shared >= 10 would re-derive "warn"
    # (0.0 < 0.90), violating the status-consistency contract.
    const = {f"gene{i:02d}": 100.0 for i in range(12)}
    a = _write_counts(tmp_path / "a.tsv", const)
    b = _write_counts(tmp_path / "b.tsv", dict(const))
    capture: dict[str, dict[str, float]] = {}
    results = evaluate_count_concordance(a, b, assay="rnaseq", capture_metrics=capture)

    spearman = next(r for r in results if r.check == "spearman_concordance")
    assert spearman.status == "unverified"
    assert capture["S1"] == {"n_shared": 12.0}
    assert _predicted("concordance_spearman", capture) == "unverified"


def test_count_capture_absent_param_byte_identical(tmp_path):
    mapping = {f"gene{i:02d}": (i + 1) * 100 for i in range(12)}
    a = _write_counts(tmp_path / "a.tsv", mapping)
    b = _write_counts(tmp_path / "b.tsv", dict(mapping))

    plain = count_results(a, b)
    capture: dict[str, dict[str, float]] = {}
    captured = count_results(a, b, capture_metrics=capture)

    assert _dump(captured) == _dump(plain)
    assert capture["S1"] == {"value": 1.0, "n_shared": 12.0}


# --- single-cell: the shared count core carries the out-param -------------------


def test_sc_count_capture_uses_count_core(tmp_path):
    mapping = {f"gene{i:02d}": (i + 1) * 100 for i in range(12)}
    primary = _mtx_pseudobulk(tmp_path / "primary", mapping)
    second = _write_dense_counts(tmp_path / "second.tsv", dict(mapping))

    capture: dict[str, dict[str, float]] = {}
    results = evaluate_sc_count_concordance(
        primary, second, assay="scrnaseq", capture_metrics=capture
    )

    assert capture["S1"] == {"value": 1.0, "n_shared": 12.0}
    assert _module_worst(results) == "pass"
    assert _predicted("concordance_spearman", capture) == "pass"


# --- Phase 2: verify-time capture hook (PRD R2/R3/R-risk-1) --------------------
# Fixtures mirror tests/test_cli.py's --concordance-* helpers so the CLI-level
# capture assertions exercise the same runs the CLI tests do. The hook must
# append exactly ONE pending case per concordance invocation, dedupe on
# repeat, never write for a no-flag verify or an honest skip, and stay
# invisible to every user-facing output byte (spec AC3/AC4/AC6/AC7).

runner = CliRunner()

_VCF_HEADER = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
)
_VCF_SITES_A = (
    "chr1\t100\t.\tA\tT\t50\tPASS\t.\tGT\t0/1\n"
    "chr1\t200\t.\tC\tG\t50\tPASS\t.\tGT\t1/1\n"
    "chr2\t300\t.\tG\tA\t50\tPASS\t.\tGT\t0/1\n"
)
_VCF_SITES_CONCORDANT = (
    "chr1\t100\t.\tA\tT\t50\tPASS\t.\tGT\t0|1\n"
    "chr1\t200\t.\tC\tG\t50\tPASS\t.\tGT\t1/1\n"
    "chr2\t300\t.\tG\tA\t50\tPASS\t.\tGT\t1/0\n"
)
_COUNTS_PRIMARY = {f"ENSG{i:05d}": float(10 * (i + 1)) for i in range(12)}
_COUNTS_CONCORDANT = dict(_COUNTS_PRIMARY)


def _write_germline_run_with_vcf(runs_dir, run_id, vcf_body):
    """A variant_calling run whose results/ holds a primary ``*.vcf.gz`` call set."""
    import gzip as _gzip

    from contig.bundle import compute_output_checksums

    run_dir = Path(runs_dir) / run_id
    results = run_dir / "results"
    results.mkdir(parents=True, exist_ok=True)
    primary = results / "S1.vcf.gz"
    primary.write_bytes(_gzip.compress((_VCF_HEADER + vcf_body).encode()))
    record = RunRecord(
        run_id=run_id,
        pipeline="nf-core/sarek",  # variant_calling assay
        pipeline_revision="3.5.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        output_checksums=compute_output_checksums(results),
    )
    write_bundle(record, run_dir)
    return run_dir


def _write_second_vcf(tmp_path, name, vcf_body):
    import gzip as _gzip

    path = tmp_path / name
    path.write_bytes(_gzip.compress((_VCF_HEADER + vcf_body).encode()))
    return path


def _counts_tsv(counts):
    """Render a gene-count matrix TSV: a header row then one row per gene."""
    lines = ["gene_id\tgene_name\tS1"]
    for gene, count in counts.items():
        lines.append(f"{gene}\t{gene}_name\t{count}")
    return "\n".join(lines) + "\n"


def _write_rnaseq_run_with_counts(runs_dir, run_id, counts):
    """An rnaseq run whose results/ holds a primary Salmon gene-count matrix."""
    from contig.bundle import compute_output_checksums

    run_dir = Path(runs_dir) / run_id
    results = run_dir / "results"
    results.mkdir(parents=True, exist_ok=True)
    primary = results / "salmon.merged.gene_counts.tsv"
    primary.write_text(_counts_tsv(counts))
    record = RunRecord(
        run_id=run_id,
        pipeline="nf-core/rnaseq",  # rnaseq assay
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        output_checksums=compute_output_checksums(results),
    )
    write_bundle(record, run_dir)
    return run_dir


def _write_second_counts(tmp_path, name, counts):
    path = tmp_path / name
    path.write_text(_counts_tsv(counts))
    return path


def _pending_cases(runs_dir) -> list[VerificationCase]:
    """The pending sidecar's cases; [] when the file does not exist yet."""
    path = Path(runs_dir) / "pending_verify_corpus.jsonl"
    if not path.exists():
        return []
    return [
        VerificationCase.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def test_verify_concordance_captures_pending_case(tmp_path):
    _write_germline_run_with_vcf(tmp_path, "g1", _VCF_SITES_A)
    second = _write_second_vcf(tmp_path, "second.vcf.gz", _VCF_SITES_CONCORDANT)
    result = runner.invoke(
        app,
        ["verify", "g1", "--runs-dir", str(tmp_path), "--concordance-vcf", str(second)],
    )
    assert result.exit_code == 0

    cases = _pending_cases(tmp_path)
    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == "g1-verify-concordance"
    assert case.source == "pending:g1"
    assert case.assay == "unknown"  # the fixture record carries no assay field
    assert case.inputs == {
        "concordance_genotype": {"S1": {"value": 1.0, "n_shared": 3.0}}
    }
    assert case.expected_verdict is None
    assert "concordance_genotype" in case.description
    assert "g1" in case.description


def test_verify_concordance_counts_captures_pending_case(tmp_path):
    _write_rnaseq_run_with_counts(tmp_path, "r1", _COUNTS_PRIMARY)
    second = _write_second_counts(tmp_path, "second.tsv", _COUNTS_CONCORDANT)
    result = runner.invoke(
        app,
        ["verify", "r1", "--runs-dir", str(tmp_path), "--concordance-counts", str(second)],
    )
    assert result.exit_code == 0

    cases = _pending_cases(tmp_path)
    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == "r1-verify-concordance"
    assert case.source == "pending:r1"
    assert case.inputs == {
        "concordance_spearman": {"S1": {"value": 1.0, "n_shared": 12.0}}
    }
    assert case.expected_verdict is None


def test_verify_without_concordance_flag_writes_nothing(tmp_path):
    _write_germline_run_with_vcf(tmp_path, "g2", _VCF_SITES_A)
    result = runner.invoke(app, ["verify", "g2", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert not (tmp_path / "pending_verify_corpus.jsonl").exists()


def test_verify_concordance_honest_skip_writes_nothing(tmp_path):
    # A non-germline assay with --concordance-vcf: the existing skip path
    # returns [] (with a note), so nothing may be captured.
    _write_rnaseq_run_with_counts(tmp_path, "rna", _COUNTS_PRIMARY)
    second = _write_second_vcf(tmp_path, "second.vcf.gz", _VCF_SITES_A)
    result = runner.invoke(
        app,
        ["verify", "rna", "--runs-dir", str(tmp_path), "--concordance-vcf", str(second)],
    )
    assert result.exit_code == 0
    assert "germline" in result.output.lower()
    assert not _pending_cases(tmp_path)


def test_verify_concordance_repeat_appends_once(tmp_path):
    _write_germline_run_with_vcf(tmp_path, "g3", _VCF_SITES_A)
    second = _write_second_vcf(tmp_path, "second.vcf.gz", _VCF_SITES_CONCORDANT)
    argv = ["verify", "g3", "--runs-dir", str(tmp_path), "--concordance-vcf", str(second)]
    first = runner.invoke(app, argv)
    again = runner.invoke(app, argv)
    assert first.exit_code == 0
    assert again.exit_code == 0

    cases = _pending_cases(tmp_path)
    assert len(cases) == 1
    assert cases[0].case_id == "g3-verify-concordance"


def test_verify_capture_output_byte_stable(tmp_path):
    # The capture channel must be invisible to every output byte: the append
    # path (fresh runs-dir) and the dedupe path (pre-seeded sidecar) must echo
    # byte-identical text and --json output.
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_c = tmp_path / "c"
    for d in (dir_a, dir_b, dir_c):
        _write_rnaseq_run_with_counts(d, "s", _COUNTS_PRIMARY)
    second = _write_second_counts(tmp_path, "second.tsv", _COUNTS_CONCORDANT)
    base = ["verify", "s", "--concordance-counts", str(second)]

    out_a_text = runner.invoke(app, base + ["--runs-dir", str(dir_a)])
    assert out_a_text.exit_code == 0
    out_c_json = runner.invoke(app, base + ["--runs-dir", str(dir_c), "--json"])
    assert out_c_json.exit_code == 0
    runner.invoke(app, base + ["--runs-dir", str(dir_b)])  # creates the sidecar
    out_b_text = runner.invoke(app, base + ["--runs-dir", str(dir_b)])
    out_b_json = runner.invoke(app, base + ["--runs-dir", str(dir_b), "--json"])
    assert out_b_text.exit_code == 0
    assert out_b_json.exit_code == 0

    assert out_a_text.output == out_b_text.output
    assert out_c_json.output == out_b_json.output


def test_verify_capture_writes_nothing_to_run_dir(tmp_path):
    run_dir = _write_germline_run_with_vcf(tmp_path, "g4", _VCF_SITES_A)
    second = _write_second_vcf(tmp_path, "second.vcf.gz", _VCF_SITES_CONCORDANT)
    before = sorted(
        p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*") if p.is_file()
    )
    result = runner.invoke(
        app,
        ["verify", "g4", "--runs-dir", str(tmp_path), "--concordance-vcf", str(second)],
    )
    assert result.exit_code == 0
    after = sorted(
        p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*") if p.is_file()
    )
    assert after == before
