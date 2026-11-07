"""Tests for biomarker report contracts."""

from contig.biomarkers.models import BiomarkerEntry, BiomarkerMeta, BiomarkerReport


def test_entry_and_report_round_trip():
    report = BiomarkerReport(
        entries=[BiomarkerEntry(name="TMB computed", value="5.00", unit="mut/Mb", status="computed")],
        meta=BiomarkerMeta(definition="PASS variants"),
    )
    payload = report.meta.model_dump_json()
    assert "PASS variants" in payload
    assert report.entries[0].name == "TMB computed"
