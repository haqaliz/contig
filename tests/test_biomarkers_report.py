"""Tests for biomarker report building and rendering."""

import json
from pathlib import Path

from contig.biomarkers.report import build_report, render_json, render_tsv

FIX = Path(__file__).parent / "fixtures" / "biomarkers"
VCF = FIX / "variants.vcf"
BED = FIX / "callable.bed"


def _report(**kwargs):
    return build_report(VCF, BED, **kwargs)


def test_computed_tmb_without_a_reported_value():
    report = _report()
    tmb = next(entry for entry in report.entries if entry.name == "TMB computed")
    assert tmb.value == "5.00"
    assert tmb.status == "computed"
    assert tmb.unit == "mut/Mb"


def test_reported_tmb_match_and_divergence():
    match = _report(reported_tmb=5.5, tmb_tolerance=0.2)
    assert next(e for e in match.entries if e.name == "TMB computed").status == "match"
    divergent = _report(reported_tmb=10.0, tmb_tolerance=0.2)
    assert next(e for e in divergent.entries if e.name == "TMB computed").status == "divergent"


def test_invalid_reported_tmb_is_unverified():
    report = _report(reported_tmb=0.0)
    assert next(e for e in report.entries if e.name == "TMB computed").status == "unverified"


def test_msi_loh_cnv_are_not_verified():
    report = _report(reported_msi="MSI-H", reported_loh="LOH", reported_cnv="CNV")
    for name in ("MSI", "LOH", "CNV"):
        entry = next(e for e in report.entries if e.name == name)
        assert entry.status == "not_verified"
        assert entry.value


def test_no_drug_or_treatment_recommendation():
    report = _report()
    text = render_tsv(report).lower()
    assert "drug" not in text
    assert "nccn" not in text
    assert "treatment" not in text


def test_json_meta_has_sources_and_definition():
    payload = json.loads(render_json(_report()))
    assert payload["meta"]["definition"].startswith("PASS variants")
    assert {source["kind"] for source in payload["meta"]["sources"]} == {"vcf", "callable_bed"}
    assert payload["meta"]["tolerance"] == 0.2
    assert payload["meta"]["contig_version"]
