"""Tests for the derived-data build script's homology selection logic."""

import gzip
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "build_derived_data.py"


def _module():
    spec = importlib.util.spec_from_file_location("build_derived_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(transcript="TX1", *, mane=False, canonical=False, start=0):
    return ("1", start, start + 10, "GENE", transcript, "1", mane, canonical)


def test_mane_select_wins():
    rows = [_row("TX1"), _row("TX2", mane=True), _row("TX3", canonical=True)]
    selected = _module()._representative_rows(rows)
    assert {row[4] for row in selected} == {"TX2"}


def test_canonical_wins_without_mane():
    rows = [_row("TX1"), _row("TX2", canonical=True)]
    selected = _module()._representative_rows(rows)
    assert {row[4] for row in selected} == {"TX2"}


def test_fallback_uses_the_transcript_with_most_exons():
    rows = [_row("TX1"), _row("TX2"), _row("TX2", start=20)]
    selected = _module()._representative_rows(rows)
    assert {row[4] for row in selected} == {"TX2"}
    assert len(selected) == 2


def test_config_validation_rejects_an_asymmetric_pair(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "HOMOLOGY_PAIRS", {"A": ("B",), "B": ()})
    monkeypatch.setattr(module, "REASONS", {"A": "x", "B": "y"})
    with pytest.raises(SystemExit, match="not symmetric"):
        module._validate_config()


def test_parse_filters_biotypes_and_keeps_pseudogenes(tmp_path, monkeypatch):
    module = _module()
    gtf = tmp_path / "tiny.gtf.gz"
    gtf.write_bytes(
        gzip.compress(
            (
                '1\t.\texon\t1\t10\t.\t+\t.\tgene_name "A"; transcript_id "TXA"; '
                'transcript_biotype "protein_coding"; tag "MANE_Select";\n'
                '1\t.\texon\t21\t30\t.\t+\t.\tgene_name "A"; transcript_id "TXBAD"; '
                'transcript_biotype "retained_intron";\n'
                '1\t.\texon\t41\t50\t.\t+\t.\tgene_name "B"; transcript_id "TXB"; '
                'transcript_biotype "transcribed_unprocessed_pseudogene"; '
                'tag "Ensembl_canonical";\n'
            ).encode()
        )
    )
    monkeypatch.setattr(module, "GTF", gtf)
    monkeypatch.setattr(module, "PANEL_GENES", {"A"})
    monkeypatch.setattr(module, "HOMOLOGY_PAIRS", {"A": ("B",), "B": ("A",)})
    monkeypatch.setattr(module, "REASONS", {"A": "x", "B": "y"})
    by_gene = module.parse()
    assert {row[4] for row in by_gene["A"]} == {"TXA"}
    assert {row[4] for row in by_gene["B"]} == {"TXB"}
