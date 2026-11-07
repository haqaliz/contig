"""Tests for the optional gnomAD API client and cache."""

from pathlib import Path

import pytest

from contig.variants.gnomad import GNOMAD_MAX_SITES, load_gnomad
from contig.variants.models import VariantKey
from contig.variants.table import build_table

FIX = Path(__file__).parent / "fixtures" / "variants"
SAMPLE = FIX / "sample.vcf"


class FakeClient:
    def __init__(self):
        self.calls: list[str] = []

    def fetch(self, variant_id: str) -> dict | None:
        self.calls.append(variant_id)
        if variant_id == "1-100-A-G":
            return {"genome": {"ac": 2, "an": 1000, "af": 0.002}}
        return None


def test_load_gnomad_maps_and_caches(tmp_path):
    cache = tmp_path / "cache.json"
    sites = {VariantKey("1", 100, "A", "G"), VariantKey("1", 200, "A", "G")}
    evidence, provenance = load_gnomad(sites, FakeClient(), cache_path=cache)
    assert evidence[VariantKey("1", 100, "A", "G")].af == 0.002
    assert VariantKey("1", 200, "A", "G") not in evidence
    assert cache.is_file()
    assert provenance.kind == "gnomad_api"
    assert "1 of 2" in provenance.note

    class Counting:
        def __init__(self):
            self.calls: list[str] = []

        def fetch(self, variant_id: str):
            self.calls.append(variant_id)
            return None

    client = Counting()
    cached, _ = load_gnomad(sites, client, cache_path=cache)
    assert cached[VariantKey("1", 100, "A", "G")].an == 1000
    assert "1-100-A-G" not in client.calls


def test_load_gnomad_caps_the_site_count():
    sites = {VariantKey("1", index, "A", "G") for index in range(GNOMAD_MAX_SITES + 1)}
    with pytest.raises(ValueError, match="limited"):
        load_gnomad(sites, FakeClient())


def test_build_table_with_gnomad_api():
    table = build_table(SAMPLE, gnomad_api=True, gnomad_client=FakeClient())
    row = next(row for row in table.rows if row.key.pos == 100)
    assert row.gnomad_af == 0.002
    assert row.gnomad_an == 1000
    assert any(source.kind == "gnomad_api" for source in table.meta.sources)


def test_frequencies_and_gnomad_api_are_mutually_exclusive():
    with pytest.raises(ValueError, match="either"):
        build_table(SAMPLE, frequencies=FIX / "frequencies.tsv", gnomad_api=True, gnomad_client=FakeClient())
