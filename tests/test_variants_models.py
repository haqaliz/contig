"""Tests for the variant workbench contracts."""

import json

import pytest
from pydantic import ValidationError

from contig.variants.models import FilterSpec, SourceProvenance, TableMeta, VariantKey


def test_filter_spec_defaults_are_empty():
    spec = FilterSpec()
    assert spec.genes == []
    assert spec.max_af is None
    assert spec.pass_only is False


def test_filter_spec_rejects_out_of_range_af():
    with pytest.raises(ValidationError):
        FilterSpec(max_af=1.5)


def test_filter_spec_rejects_unknown_zygosity():
    with pytest.raises(ValidationError):
        FilterSpec(zygosity="mosaic")


def test_filter_spec_round_trips_through_json():
    spec = FilterSpec(genes=["BRCA1"], max_af=0.01, pass_only=True, region="17:1-100")
    again = FilterSpec.model_validate_json(spec.model_dump_json())
    assert again == spec


def test_merged_lets_explicit_flags_override_saved_spec():
    saved = FilterSpec(genes=["BRCA1"], pass_only=True)
    explicit = FilterSpec(genes=["GJB2"])
    merged = saved.merged(explicit)
    assert merged.genes == ["GJB2"]
    assert merged.pass_only is True


def test_merged_keeps_a_zero_max_af():
    saved = FilterSpec(max_af=0.01)
    merged = saved.merged(FilterSpec(max_af=0.0))
    assert merged.max_af == 0.0


def test_meta_serializes_sources_and_filters():
    meta = TableMeta(
        sources=[SourceProvenance(kind="calls", path="x.vcf", sha256="abc")],
        filters=FilterSpec(genes=["BRCA1"]),
        build="GRCh38",
        contig_version="test",
    )
    payload = json.loads(meta.model_dump_json())
    assert payload["sources"][0]["kind"] == "calls"
    assert payload["filters"]["genes"] == ["BRCA1"]
    assert payload["build"] == "GRCh38"


def test_variant_key_is_orderable():
    a = VariantKey("1", 10, "A", "G")
    b = VariantKey("1", 20, "A", "G")
    assert a < b
