"""CLI smoke tests for `contig readiness`."""

import json
from pathlib import Path

from typer.testing import CliRunner

from tests.ansi import plain

from contig.cli import app

FIX = Path(__file__).parent / "fixtures" / "readiness"
DEPTH = str(FIX / "depth.tsv")
PANEL = str(FIX / "panel.bed")
HOMOLOGY = str(FIX / "homology.bed")
GTF = str(FIX / "genes.gtf")


def _invoke(args):
    return CliRunner().invoke(app, ["readiness", *args])


def test_help_lists_the_readiness_options():
    result = _invoke(["--help"])
    assert result.exit_code == 0
    assert "--depth" in plain(result.output)
    assert "--bed" in plain(result.output)
    assert "--gtf" in plain(result.output)
    assert "--caveats" in plain(result.output)
    assert "--build" in plain(result.output)


def test_writes_a_tsv_and_prints_the_summary(tmp_path):
    out = tmp_path / "readiness.tsv"
    result = _invoke(["--depth", DEPTH, "--bed", PANEL, "--caveats", HOMOLOGY, "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text().startswith("target\tgene")
    combined = result.output + getattr(result, "stderr", "")
    assert "Research use only" in combined
    assert "4 target(s)" in combined


def test_json_output_contains_meta(tmp_path):
    out = tmp_path / "readiness.json"
    result = _invoke(["--depth", DEPTH, "--bed", PANEL, "--json", "--out", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    assert len(payload["targets"]) == 4
    assert payload["meta"]["thresholds"]["depth_threshold"] == 20


def test_missing_depth_exits_nonzero():
    result = _invoke(["--depth", str(FIX / "missing.tsv"), "--bed", PANEL])
    assert result.exit_code == 1
    assert "not found" in plain(result.output).lower()


def test_bed_and_gtf_together_exit_nonzero():
    result = _invoke(["--depth", DEPTH, "--bed", PANEL, "--gtf", GTF, "--genes", "GENE1"])
    assert result.exit_code == 1
    assert "exactly one" in plain(result.output).lower()


def test_by_gene_output(tmp_path):
    out = tmp_path / "genes.tsv"
    result = _invoke(["--depth", DEPTH, "--bed", PANEL, "--by-gene", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text().startswith("gene\ttargets")
