"""Runner-level wiring tests for the R4a capture out-params (wiring half).

Phase 3 (runner wiring) of the eval-concordance-capture slice: `_discover_qc`'s
`capture_inputs` out-param must now also populate the four R4a family keys --
`somatic_plausibility` + `concordance_somatic_overlap` (somatic assay) and
`annotation_plausibility` + `concordance_consequence` (variant-calling assays)
-- from the evaluator `capture_metrics=` out-params wired by the two preceding
commits (fa0a694, 702913f). These tests exercise
`_discover_qc(run_dir, assay, capture_inputs={...})` END-TO-END over synthetic
run dirs: real gzipped VCFs under a sarek-shaped tree, no mocks, no tool
execution, no network.

Family/sample-key conventions pinned here (matching the module-level halves):
- `capture_inputs["concordance_somatic_overlap"] == {"mutect2_vs_strelka2":
  {"value": <raw jaccard>, "n_shared": float(union)}}`, written only when both
  callers were present and the concordance was actually evaluated;
- `capture_inputs["somatic_plausibility"]` keyed by resolved sample labels: the
  tumor key carries median_vaf + somatic_variant_count + strelka_median_vaf,
  the normal key carries normal_median_vaf;
- `capture_inputs["concordance_consequence"] == {"vep_vs_snpeff": {"value":
  <raw agreement>, "n_shared": float(shared)}}`;
- `capture_inputs["annotation_plausibility"] == {"sample": {
  real_consequence_fraction, intergenic_fraction}}`, empty samples filtered
  (the rnaseq_composition precedent);
- absent the `capture_inputs` argument, the QCResult list is byte-identical to
  before (additive, back-compat).
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from contig.runner import _discover_qc

# --- shared VCF helpers -------------------------------------------------------


def _gz(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(body)
    return path


# --- somatic fixtures (sarek-shaped, both callers) ----------------------------

# Mutect2: two-sample layout, tumor/normal named via the ##*_sample= headers,
# FORMAT AF for the tumor and normal VAF derivations.
_MUT_HEADER = (
    "##fileformat=VCFv4.2\n"
    "##tumor_sample=TUMOR\n"
    "##normal_sample=NORMAL\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tNORMAL\tTUMOR\n"
)


def _mut_rec(chrom, pos, ref, alt):
    # tumor AF 0.30, normal AF 0.0, both biallelic PASS
    return (
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\tGT:AF:AD:DP\t"
        f"0/0:0.0:10,0:10\t0/1:0.30:14,6:20\n"
    )


# Strelka2: tier-count VAFs (AU/CU/GU/TU for SNVs, TAR/TIR for indels); the
# tumor column is literally named TUMOR.
_SNV_HEADER = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tNORMAL\tTUMOR\n"
)


def _snv_rec(chrom, pos, ref, alt):
    # AU=14,15 tier1 14 (REF base A), GU=6,7 tier1 6 (ALT base G)
    # -> VAF 6/20 = 0.30
    return (
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\tAU:CU:GU:TU\t"
        f"0,0:0,0:0,0:0,0\t14,15:0,0:6,7:0,0\n"
    )


_INDEL_HEADER = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tNORMAL\tTUMOR\n"
)


def _indel_rec(chrom, pos, ref, alt):
    # TAR=14,15 tier1 14, TIR=6,7 tier1 6 -> VAF 6/20 = 0.30
    return (
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\tTAR:TIR\t"
        f"0,0:0,0\t14,15:6,7\n"
    )


_SITES = [(f"chr1", 100 + i, "A", "G") for i in range(15)]


def _somatic_run(tmp_path: Path, *, with_strelka: bool = True) -> Path:
    """A synthetic sarek-shaped somatic run dir: Mutect2 + Strelka SNV/indel
    VCFs sharing all 15 PASS sites (jaccard 1.0, union 15), each caller under
    its own path component below the run dir."""
    run_dir = tmp_path / "run"
    m_dir = run_dir / "results" / "variant_calling" / "mutect2" / "T_vs_N"
    _gz(
        m_dir / "T_vs_N.mutect2.somatic.vcf.gz",
        _MUT_HEADER + "".join(_mut_rec(*site) for site in _SITES),
    )
    if with_strelka:
        s_dir = run_dir / "results" / "variant_calling" / "strelka" / "T_vs_N"
        _gz(
            s_dir / "T_vs_N.strelka.somatic_snvs.vcf.gz",
            _SNV_HEADER + "".join(_snv_rec(*site) for site in _SITES[:8]),
        )
        _gz(
            s_dir / "T_vs_N.strelka.somatic_indels.vcf.gz",
            _INDEL_HEADER + "".join(_indel_rec(*site) for site in _SITES[8:]),
        )
    return run_dir


# --- annotation fixtures (single VCF declaring BOTH CSQ and ANN) --------------

_BOTH_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL">\n'
    '##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: '
    "'Allele | Annotation | Annotation_Impact | Gene_Name'\">\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)


def _annotation_run(tmp_path: Path, n: int = 10) -> Path:
    """A synthetic variant_calling run dir with ONE annotated VCF (both CSQ and
    ANN declared); all n records are real (missense) consequences."""
    run_dir = tmp_path / "run"
    body = "".join(
        f"chr1\t{100 + i}\t.\tA\tG\t50\tPASS\t"
        "CSQ=G|missense_variant|MODERATE|GENE1;ANN=G|missense_variant|MODERATE|GENE1\n"
        for i in range(n)
    )
    _gz(run_dir / "results" / "variant_calling" / "annotated.vcf.gz", _BOTH_HEADER + body)
    return run_dir


# --- wiring tests --------------------------------------------------------------


def test_discover_qc_captures_somatic_concordance_and_plausibility(tmp_path):
    run_dir = _somatic_run(tmp_path)

    capture_inputs: dict[str, dict[str, dict[str, float]]] = {}
    _discover_qc(run_dir, assay="somatic_variant_calling", capture_inputs=capture_inputs)

    # Concordance family: raw jaccard (15/15 shared) + float(union), under the
    # mutect2_vs_strelka2 pair key.
    assert capture_inputs["concordance_somatic_overlap"] == {
        "mutect2_vs_strelka2": {"value": 1.0, "n_shared": 15.0}
    }
    # Plausibility family: tumor key carries the Mutect2 + Strelka2 tumor-VAF
    # metrics, normal key carries normal_median_vaf (all floats).
    plaus = capture_inputs["somatic_plausibility"]
    assert plaus["TUMOR"]["median_vaf"] == pytest.approx(0.30)
    assert plaus["TUMOR"]["somatic_variant_count"] == pytest.approx(15.0)
    assert plaus["TUMOR"]["strelka_median_vaf"] == pytest.approx(0.30)
    assert plaus["NORMAL"]["normal_median_vaf"] == pytest.approx(0.0)
    # Numeric metrics only; somatic_variant_count is an int by module design
    # (the float-typed dict contract is nominal, mirroring the germline capture).
    assert all(isinstance(v, (int, float)) for m in plaus.values() for v in m.values())


def test_discover_qc_captures_annotation_concordance_and_plausibility(tmp_path):
    run_dir = _annotation_run(tmp_path)

    capture_inputs: dict[str, dict[str, dict[str, float]]] = {}
    _discover_qc(run_dir, assay="variant_calling", capture_inputs=capture_inputs)

    # Consequence-concordance family: raw agreement 10/10 + float(shared).
    assert capture_inputs["concordance_consequence"] == {
        "vep_vs_snpeff": {"value": 1.0, "n_shared": 10.0}
    }
    # Annotation plausibility family: all 10 records real (missense) -> 1.0 / 0.0.
    plaus = capture_inputs["annotation_plausibility"]
    assert "sample" in plaus
    assert plaus["sample"]["real_consequence_fraction"] == pytest.approx(1.0)
    assert plaus["sample"]["intergenic_fraction"] == pytest.approx(0.0)
    assert all(isinstance(v, float) for v in plaus["sample"].values())


def test_discover_qc_writes_nothing_without_param(tmp_path):
    # No capture_inputs arg: no crash, and the emitted QCResult list is
    # byte-identical to the same call WITH the (empty) out-param.
    somatic_plain = _discover_qc(_somatic_run(tmp_path), assay="somatic_variant_calling")
    somatic_captured = _discover_qc(
        _somatic_run(tmp_path), assay="somatic_variant_calling", capture_inputs={}
    )
    assert somatic_captured == somatic_plain
    assert somatic_captured  # the checks still ran

    annotation_plain = _discover_qc(_annotation_run(tmp_path), assay="variant_calling")
    annotation_captured = _discover_qc(
        _annotation_run(tmp_path), assay="variant_calling", capture_inputs={}
    )
    assert annotation_captured == annotation_plain


def test_discover_qc_skips_concordance_when_one_caller_missing(tmp_path):
    run_dir = _somatic_run(tmp_path, with_strelka=False)

    capture_inputs: dict[str, dict[str, dict[str, float]]] = {}
    _discover_qc(run_dir, assay="somatic_variant_calling", capture_inputs=capture_inputs)

    # Plausibility is still captured from the lone Mutect2 VCF...
    assert "somatic_plausibility" in capture_inputs
    assert capture_inputs["somatic_plausibility"]["TUMOR"][
        "median_vaf"
    ] == pytest.approx(0.30)
    # ...but the cross-caller concordance family is honestly absent (no Strelka
    # pair to corroborate against; never an empty or fabricated key).
    assert "concordance_somatic_overlap" not in capture_inputs
