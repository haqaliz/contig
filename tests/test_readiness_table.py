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
