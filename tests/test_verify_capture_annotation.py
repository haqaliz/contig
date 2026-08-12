"""Tests for the annotation concordance + plausibility capture out-params (R4a,
module-level half).

Phase 2 of the eval-concordance-capture fold-in: the same `capture_metrics`
out-param precedent as `evaluate_variant_plausibility` (variant_metrics.py:151-192)
threaded through the annotation evaluators, exercised DIRECTLY (the runner wiring
is a later step by another agent). Pins:

- `evaluate_annotation_concordance_from_run(..., capture_metrics=...)` writes
  `capture_metrics["vep_vs_snpeff"] = {"value": <raw agreement>, "n_shared":
  float(<shared>)}` for both the single-vcf-both and two-file layouts, and on
  the too-few-shared-variants path (a low n_shared still captures; it re-derives
  to unverified downstream in `_concordance_status`, verify_corpus.py:159-180).
- The `_one_annotator_only` path writes NOTHING (honest absence).
- `evaluate_annotation_plausibility(..., capture_metrics=...)` writes
  `capture_metrics["sample"] = {metric: float}` for the computable metrics only
  (the sample-key convention mirrors the germline capture's default sample name
  and this module's check-name convention, "<check>:<label>" with label default
  "sample"); None metrics are omitted, never stored.
- Emitted QCResult messages stay byte-identical to the no-param calls.

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from contig.verification.annotation_concordance import (
    evaluate_annotation_concordance_from_run,
)
from contig.verification.annotation_plausibility import (
    evaluate_annotation_plausibility,
)

# VEP CSQ header: Format declares Consequence at index 1, SYMBOL at index 3.
VEP_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

# SnpEff ANN header: fixed layout, consequence ("Annotation") at index 1,
# Gene_Name at index 3.
ANN_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: '
    "'Allele | Annotation | Annotation_Impact | Gene_Name'\">\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

# A single VCF declaring BOTH CSQ and ANN headers (single-vcf-both layout).
BOTH_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL">\n'
    '##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: '
    "'Allele | Annotation | Annotation_Impact | Gene_Name'\">\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

# VEP CSQ header whose Format string omits "Consequence" -> unresolvable.
CSQ_NO_CONSEQUENCE_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|IMPACT|SYMBOL">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)


def _write_gz(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    with gzip.open(p, "wt") as fh:
        fh.write(body)
    return p


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


def _sites(n: int, chrom: str = "chr1", start: int = 100):
    """n distinct (chrom, pos, ref, alt) site tuples, deterministic and disjoint."""
    return [(chrom, start + i, "A", "G") for i in range(n)]


def _csq_body(sites, term: str = "missense_variant", symbol: str = "GENE1") -> str:
    return "".join(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\tCSQ={alt}|{term}|MODERATE|{symbol}\n"
        for chrom, pos, ref, alt in sites
    )


def _ann_body(sites, term: str = "missense_variant", symbol: str = "GENE1") -> str:
    return "".join(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\tANN={alt}|{term}|MODERATE|{symbol}\n"
        for chrom, pos, ref, alt in sites
    )


def _both_body(sites, term: str = "missense_variant", symbol: str = "GENE1") -> str:
    return "".join(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\t"
        f"CSQ={alt}|{term}|MODERATE|{symbol};ANN={alt}|{term}|MODERATE|{symbol}\n"
        for chrom, pos, ref, alt in sites
    )


# --- Concordance capture: single-vcf-both layout --------------------------------


def test_capture_annotation_concordance_single_vcf_both(tmp_path):
    sites = _sites(10)
    _write_gz(tmp_path, "both.vcf.gz", BOTH_HEADER + _both_body(sites))

    capture: dict[str, dict[str, float]] = {}
    results = evaluate_annotation_concordance_from_run(
        tmp_path, capture_metrics=capture
    )
    baseline = evaluate_annotation_concordance_from_run(tmp_path)

    assert capture["vep_vs_snpeff"] == {"value": 1.0, "n_shared": 10.0}
    assert isinstance(capture["vep_vs_snpeff"]["value"], float)
    assert isinstance(capture["vep_vs_snpeff"]["n_shared"], float)
    # The out-param must not change the emitted QCResults (M5b: byte-identical
    # messages; full equality is the stronger pin).
    assert results == baseline
    assert [r.message for r in results] == [r.message for r in baseline]
    assert results[0].status == "pass"


# --- Concordance capture: two-file layout ----------------------------------------


def test_capture_annotation_concordance_two_file(tmp_path):
    sites = _sites(10)
    _write_gz(tmp_path, "vep.vcf.gz", VEP_HEADER + _csq_body(sites))
    _write_gz(tmp_path, "snpeff.vcf.gz", ANN_HEADER + _ann_body(sites))

    capture: dict[str, dict[str, float]] = {}
    results = evaluate_annotation_concordance_from_run(
        tmp_path, capture_metrics=capture
    )
    baseline = evaluate_annotation_concordance_from_run(tmp_path)

    assert capture["vep_vs_snpeff"] == {"value": 1.0, "n_shared": 10.0}
    assert results == baseline
    assert results[0].status == "pass"


# --- Concordance capture: one-annotator-only writes NOTHING ----------------------


def test_capture_annotation_concordance_one_annotator_only_empty(tmp_path):
    sites = _sites(10)
    _write_gz(tmp_path, "vep.vcf.gz", VEP_HEADER + _csq_body(sites))

    capture: dict[str, dict[str, float]] = {}
    results = evaluate_annotation_concordance_from_run(
        tmp_path, capture_metrics=capture
    )

    # Honest absence: only one annotator ran, there is nothing to corroborate.
    assert capture == {}
    by_check = {r.check: r for r in results}
    assert by_check["consequence_concordance"].status == "unverified"
    assert by_check["gene_symbol_concordance"].status == "unverified"
    assert "only VEP annotation is present" in by_check["consequence_concordance"].message


# --- Concordance capture: too-few-shared path still captures ---------------------


def test_capture_annotation_concordance_too_few_shared(tmp_path):
    # Only 5 shared sites (< _MIN_SHARED_VARIANTS=10): the QCResult degrades to
    # unverified, but the RAW agreement + shared count are still captured (the
    # downstream _concordance_status re-derives unverified from n_shared < 10).
    sites = _sites(5)
    _write_gz(tmp_path, "both.vcf.gz", BOTH_HEADER + _both_body(sites))

    capture: dict[str, dict[str, float]] = {}
    results = evaluate_annotation_concordance_from_run(
        tmp_path, capture_metrics=capture
    )

    assert capture["vep_vs_snpeff"] == {"value": 1.0, "n_shared": 5.0}
    assert results[0].status == "unverified"
    assert results[0].value is None


# --- Annotation plausibility capture ---------------------------------------------


def test_capture_annotation_plausibility_metrics(tmp_path):
    # 2 real (missense) + 1 intergenic -> real_consequence_fraction 2/3,
    # intergenic_fraction 1/3; both metrics captured as floats under the
    # "sample" key (the default label the check names use).
    body = VEP_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant|MODERATE|BRCA1\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T|missense_variant|MODERATE|BRCA1\n"
        "chr1\t300\t.\tG\tA\t50\tPASS\tCSQ=A|intergenic_variant|MODIFIER|.\n"
    )
    vcf = _write(tmp_path, "vep.vcf", body)

    capture: dict[str, dict[str, float]] = {}
    evaluate_annotation_plausibility(vcf, capture_metrics=capture)

    captured = capture["sample"]
    assert captured["real_consequence_fraction"] == pytest.approx(2 / 3)
    assert captured["intergenic_fraction"] == pytest.approx(1 / 3)
    assert all(isinstance(v, float) for v in captured.values())


def test_capture_annotation_plausibility_omits_uncomputable(tmp_path):
    # Unresolvable CSQ Format -> both metrics None -> nothing computable, so
    # the capture holds an empty sample dict: None values are never stored.
    body = CSQ_NO_CONSEQUENCE_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|MODERATE|BRCA1\n"
    )
    vcf = _write(tmp_path, "unresolvable.vcf", body)

    capture: dict[str, dict[str, float]] = {}
    evaluate_annotation_plausibility(vcf, capture_metrics=capture)

    assert capture["sample"] == {}
    assert all(
        value is not None
        for sample in capture.values()
        for value in sample.values()
    )
