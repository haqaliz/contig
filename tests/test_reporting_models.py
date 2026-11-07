"""Tests for report spec and metadata contracts."""

import pytest
from pydantic import ValidationError

from contig.reporting.models import ReportMeta, ReportSpec, Reviewer


def test_spec_defaults_are_safe():
    spec = ReportSpec()
    assert spec.template == "publication"
    assert spec.reviewer is None
    assert spec.max_rows == 100


def test_spec_rejects_unknown_template():
    with pytest.raises(ValidationError):
        ReportSpec(template="clinical")


def test_spec_bounds_max_rows():
    with pytest.raises(ValidationError):
        ReportSpec(max_rows=0)
    with pytest.raises(ValidationError):
        ReportSpec(max_rows=10001)


def test_spec_round_trips_with_reviewer():
    spec = ReportSpec(
        title="T",
        template="audit",
        reviewer=Reviewer(name="R", role="PI", reviewed_at="2026-11-07"),
    )
    again = ReportSpec.model_validate_json(spec.model_dump_json())
    assert again == spec
    assert again.reviewer.name == "R"


def test_meta_round_trips():
    meta = ReportMeta(run_id="r1", contig_version="1.0.0", html_sha256="abc")
    payload = ReportMeta.model_validate_json(meta.model_dump_json())
    assert payload.run_id == "r1"
    assert payload.generated_at
