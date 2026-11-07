"""Tests for the ClinVar, Iranome, and frequency joins."""

from pathlib import Path

import pytest

from contig.variants.sources import (
    infer_build_from_vcf,
    load_clinvar,
    load_frequencies,
    load_iranome,
)
from contig.variants.vcf import read_variants

FIX = Path(__file__).parent / "fixtures" / "variants"
SAMPLE = FIX / "sample.vcf"
CLINVAR = FIX / "clinvar.vcf"
IRANOME = FIX / "iranome.tsv"
FREQ = FIX / "frequencies.tsv"


def _sites():
    rows, _ = read_variants(SAMPLE)
    return {row.key for row in rows}


def test_infers_build_from_clinvar_header():
    assert infer_build_from_vcf(CLINVAR) == "GRCh37"


def test_clinvar_joins_by_site_and_surfaces_fields():
    evidence, provenance = load_clinvar(CLINVAR, _sites(), build="GRCh37")
    brca1 = next(key for key in evidence if key.pos == 43057063)
    assert evidence[brca1].significance == "Pathogenic"
    assert "multiple_submitters" in evidence[brca1].review_status
    assert "Breast" in evidence[brca1].condition
    assert evidence[brca1].variant_type == "Duplication"
    assert provenance.kind == "clinvar"
    assert provenance.build == "GRCh37"
    assert provenance.sha256


def test_clinvar_does_not_join_a_site_outside_the_input():
    evidence, _ = load_clinvar(CLINVAR, _sites(), build="GRCh37")
    assert all(key.pos != 999 for key in evidence)


def test_clinvar_multiallelic_sites_are_keyed_per_alt():
    evidence, _ = load_clinvar(CLINVAR, _sites(), build="GRCh37")
    at_200 = [key for key in evidence if key.pos == 200]
    by_alt = {key.alt: evidence[key] for key in at_200}
    assert by_alt["T"].significance == "Likely_pathogenic"
    assert by_alt["G"].significance == "Benign"


def test_clinvar_missing_file_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_clinvar(tmp_path / "missing.vcf", set())


def test_iranome_joins_on_grch37():
    evidence, provenance = load_iranome(IRANOME, _sites(), build="GRCh37")
    key = next(key for key in evidence if key.pos == 43057063)
    assert evidence[key].af == 0.001
    assert evidence[key].ac == 2
    assert provenance.build == "GRCh37"


def test_iranome_is_skipped_on_grch38_with_a_note():
    evidence, provenance = load_iranome(IRANOME, _sites(), build="GRCh38")
    assert evidence == {}
    assert "skipped" in provenance.note
    assert "GRCh37" in provenance.note


def test_frequency_tsv_normalizes_uppercase_header():
    evidence, provenance = load_frequencies(FREQ, _sites())
    key = next(key for key in evidence if key.pos == 43057063)
    assert evidence[key].af == 0.0001
    assert evidence[key].an == 100000
    assert provenance.kind == "frequencies"


def test_frequency_missing_site_is_absent():
    evidence, _ = load_frequencies(FREQ, _sites())
    assert all(key.pos != 999 for key in evidence)
