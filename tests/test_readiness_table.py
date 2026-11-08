"""Tests for the readiness table builder and renderers."""

import json
from pathlib import Path

import pytest

from contig.readiness.models import ReadinessThresholds
from contig.readiness.table import COLUMNS, build_readiness, render_json, render_tsv

FIX = Path(__file__).parent / "fixtures" / "readiness"
DEPTH = FIX / "depth.tsv"
PANEL = FIX / "panel.bed"
HOMOLOGY = FIX / "homology.bed"
GTF = FIX / "genes.gtf"


def _table(**kwargs):
    defaults = dict(depth=DEPTH, bed=PANEL, caveats=HOMOLOGY)
    defaults.update(kwargs)
    return build_readiness(**defaults)


def test_builds_one_row_per_target():
    table = _table()
    assert len(table.rows) == 4
    assert {row.target.name for row in table.rows} == {"GENE1", "GENE2", "GENE3", "GENE4"}
    assert {source.kind for source in table.meta.sources} == {"depth", "targets", "caveats"}


def test_tsv_has_the_documented_header_and_states():
    text = render_tsv(_table())
    lines = text.splitlines()
    assert lines[0].split("\t") == COLUMNS
    assert "not-interpretable" in text
    assert "caution" in text
    assert "ready" in text
    assert "GENE3" in text


def test_json_meta_records_sources_thresholds_and_version():
    payload = json.loads(render_json(_table(thresholds=ReadinessThresholds(depth_threshold=15))))
    assert payload["meta"]["thresholds"]["depth_threshold"] == 15
    assert payload["meta"]["generated_at"]
    assert payload["meta"]["contig_version"]
    assert len(payload["meta"]["sources"]) == 3
    assert len(payload["targets"]) == 4


def test_same_inputs_produce_identical_tsv():
    assert render_tsv(_table()) == render_tsv(_table())


def test_gtf_targets_work_without_a_bed():
    table = _table(bed=None, gtf=GTF, genes={"GENE1"}, caveats=None)
    assert len(table.rows) == 2
    assert {row.target.transcript for row in table.rows} == {"ENST1"}
    assert {source.kind for source in table.meta.sources} == {"depth", "targets"}


def test_bed_and_gtf_are_mutually_exclusive():
    with pytest.raises(ValueError):
        build_readiness(DEPTH, bed=PANEL, gtf=GTF, genes={"GENE1"})
    with pytest.raises(ValueError):
        build_readiness(DEPTH)


def test_missing_depth_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_readiness(tmp_path / "missing.tsv", bed=PANEL)


def test_gene_summary_aggregates_exons():
    table = _table()
    genes = {gene.gene: gene for gene in table.genes}
    assert set(genes) == {"GENE1", "GENE2", "GENE3", "GENE4"}
    assert genes["GENE1"].readiness == "caution"
    assert genes["GENE3"].readiness == "not-interpretable"
    assert genes["GENE4"].readiness == "ready"
    assert genes["GENE4"].targets == 1


def test_by_gene_tsv_and_json():
    from contig.readiness.table import render_gene_tsv, render_json
    table = _table()
    text = render_gene_tsv(table)
    assert text.startswith("gene\ttargets")
    assert "GENE4" in text
    payload = json.loads(render_json(table))
    assert len(payload["genes"]) == 4


def test_meta_records_build_and_caveat_coverage():
    table = _table(build="GRCh38")
    assert table.meta.build == "GRCh38"
    assert table.meta.caveats_checked is True
    assert table.meta.caveat_regions > 0
    unchecked = _table(caveats=None)
    assert unchecked.meta.caveats_checked is False
    assert unchecked.meta.caveat_regions == 0


def test_bed3_gets_gene_annotation_guidance(tmp_path):
    bed3 = tmp_path / "panel.bed"
    bed3.write_text("1\t0\t100\n")
    table = build_readiness(DEPTH, bed=bed3)
    assert table.genes == []
    assert any("BED3" in note for note in table.meta.notes)


def test_disjoint_chromosomes_get_a_build_warning(tmp_path):
    depth = tmp_path / "depth.tsv"
    depth.write_text("99\t1\t30\n")
    table = build_readiness(depth, bed=PANEL)
    assert any("no chromosome names shared" in note for note in table.meta.notes)
