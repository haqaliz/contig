"""Tests for the self-contained HTML renderer."""

import json
from pathlib import Path

from contig.reporting.inputs import input_record, load_run_bundle
from contig.reporting.models import ReportSpec
from contig.reporting.render import render_html

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"
READINESS = FIX / "readiness.json"
SPEC = FIX / "spec.json"


def _render(spec=None, signature=None):
    record = load_run_bundle(RUNS, "r1")
    spec = spec or ReportSpec.model_validate_json(SPEC.read_text())
    inputs = [
        input_record("run_record", RUNS / "r1" / "run_record.json"),
        input_record("variants", VARIANTS),
        input_record("readiness", READINESS),
    ]
    return render_html(
        record,
        spec,
        variants=json.loads(VARIANTS.read_text()),
        readiness=json.loads(READINESS.read_text()),
        inputs=inputs,
        signature=signature,
    )


def test_publication_sections_and_data():
    html = _render()
    assert "BRCA1 panel review" in html
    assert "Research use only" in html
    assert "WARN — completed with caveats" in html
    assert "mapping_rate" in html
    assert "BRCA1" in html
    assert "GENE3" in html
    assert "Dr. Reviewer" in html
    assert "Report inputs" in html


def test_tables_are_capped_with_a_note():
    html = _render()
    assert "Showing 2 of 3 variants" in html
    assert "Showing 2 of 3 targets" in html


def test_internal_template_includes_the_repair_chain():
    spec = ReportSpec.model_validate_json(SPEC.read_text())
    spec = ReportSpec.model_validate({**spec.model_dump(), "template": "internal"})
    html = _render(spec)
    assert "Repair chain" in html
    assert "STAR ran out of memory" in html


def test_audit_template_omits_the_variant_table():
    spec = ReportSpec.model_validate_json(SPEC.read_text())
    spec = ReportSpec.model_validate({**spec.model_dump(), "template": "audit"})
    html = _render(spec)
    assert "Variant evidence" not in html
    assert "Provenance" in html
    assert "Repair chain" in html
    assert "STAR ran out of memory" in html


def test_narrative_is_html_escaped():
    spec = ReportSpec.model_validate_json(SPEC.read_text())
    spec = ReportSpec.model_validate({**spec.model_dump(), "summary": "<script>alert(1)</script>"})
    html = _render(spec)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_html_is_self_contained():
    html = _render()
    assert "<script" not in html
    assert "<link" not in html
    assert "src=" not in html


def test_signature_status_is_rendered():
    signed = _render(signature={"signed": True, "signature_ok": True})
    assert "Signed; signature verified" in signed
    unsigned = _render(signature={})
    assert "Unsigned" in unsigned


def test_variant_table_includes_the_evidence_columns():
    spec = ReportSpec.model_validate_json(SPEC.read_text())
    spec = ReportSpec.model_validate({**spec.model_dump(), "max_rows": 10})
    html = _render(spec)
    assert "rs80357906" in html
    assert "0/1" in html
    assert "150" in html
    assert "Pathogenic" in html
    assert "ClinVar review" in html
    assert "unannotated" in html
