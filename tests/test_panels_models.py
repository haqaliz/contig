"""Tests for panel metadata and panel objects."""

from contig.panels.models import Panel, PanelMeta


def test_meta_defaults_and_round_trip():
    meta = PanelMeta(id="x", name="X", build="GRCh38", source="genes")
    again = PanelMeta.model_validate_json(meta.model_dump_json())
    assert again.id == "x"
    assert again.created_at
    assert again.genes == []


def test_panel_holds_bed_text():
    panel = Panel(PanelMeta(id="x", name="X", build="GRCh38", source="bed"), "1\t0\t10\n")
    assert panel.bed_text.startswith("1\t")
