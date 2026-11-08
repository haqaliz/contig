"""Tests for panel source hashes, archival, and diff."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.models import sha256_file
from contig.panels.build import (
    archive_panel,
    build_from_bed,
    build_from_genes,
    list_panels,
    load_panel,
    write_panel,
)
from contig.panels.diff import panel_diff

FIX = Path(__file__).parent / "fixtures" / "panels"
GTF = FIX / "genes.gtf"
HGNC = FIX / "hgnc.tsv"
BED = FIX / "panel.bed"


def test_gene_panel_records_gtf_and_hgnc_hashes():
    panel = build_from_genes(["BRCA1"], GTF, name="Hereditary", hgnc_path=HGNC)
    sources = {source.kind: source for source in panel.meta.sources}
    assert set(sources) == {"gtf", "hgnc"}
    assert sources["gtf"].sha256 == sha256_file(GTF)
    assert sources["hgnc"].sha256 == sha256_file(HGNC)


def test_bed_panel_records_the_bed_hash():
    panel = build_from_bed(BED, "Existing")
    assert [source.kind for source in panel.meta.sources] == ["bed"]
    assert panel.meta.sources[0].sha256 == sha256_file(BED)


def test_identical_rebuild_has_no_diff():
    one = build_from_genes(["BRCA1"], GTF, name="Stable")
    two = build_from_genes(["BRCA1"], GTF, name="Stable")
    assert panel_diff(one, two)["same"] is True


def test_diff_reports_gene_and_interval_changes():
    one = build_from_genes(["BRCA1"], GTF, name="Panel", version="1")
    two = build_from_genes(["BRCA1", "BRCA2"], GTF, name="Panel", version="2")
    result = panel_diff(one, two)
    assert result["same"] is False
    assert "genes" in result["meta"]
    assert "version" in result["meta"]
    assert result["added"]
    assert not result["removed"]


def test_archive_removes_from_active_registry_and_keeps_it_loadable(tmp_path):
    panel = build_from_genes(["BRCA1"], GTF, name="Archived")
    write_panel(panel, tmp_path)
    bed_path, meta_path = archive_panel(tmp_path, panel.meta.id)
    assert bed_path.is_file() and meta_path.is_file()
    assert list_panels(tmp_path) == []
    loaded = load_panel(tmp_path / "archive", panel.meta.id)
    assert loaded.meta == panel.meta
    assert loaded.bed_text == panel.bed_text


def test_archiving_does_not_overwrite_an_archived_copy(tmp_path):
    panel = build_from_genes(["BRCA1"], GTF, name="Archived")
    write_panel(panel, tmp_path)
    archive_panel(tmp_path, panel.meta.id)
    write_panel(panel, tmp_path)
    with pytest.raises(ValueError, match="already archived"):
        archive_panel(tmp_path, panel.meta.id)


def test_cli_panel_diff_and_archive(tmp_path):
    one = build_from_genes(["BRCA1"], GTF, name="Panel", version="1")
    two = build_from_genes(["BRCA1", "BRCA2"], GTF, name="Panel", version="2")
    write_panel(one, tmp_path)
    write_panel(two, tmp_path)

    diff = CliRunner().invoke(
        app, ["panel-diff", one.meta.id, two.meta.id, "--dir", str(tmp_path)]
    )
    assert diff.exit_code == 0, diff.output
    assert "Intervals added" in diff.output
    gated = CliRunner().invoke(
        app,
        ["panel-diff", one.meta.id, two.meta.id, "--dir", str(tmp_path), "--fail-on-diff"],
    )
    assert gated.exit_code == 1
    as_json = CliRunner().invoke(
        app,
        ["panel-diff", one.meta.id, two.meta.id, "--dir", str(tmp_path), "--json"],
    )
    assert as_json.exit_code == 0
    assert '"same": false' in as_json.output

    archived = CliRunner().invoke(
        app, ["panel-archive", one.meta.id, "--dir", str(tmp_path)]
    )
    assert archived.exit_code == 0, archived.output
    assert (tmp_path / "archive" / f"{one.meta.id}.bed").is_file()
