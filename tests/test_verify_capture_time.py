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

from contig.models import VerificationCase
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
