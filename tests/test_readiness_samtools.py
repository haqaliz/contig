"""Tests for the samtools-depth ingestion seam."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.readiness.depth import load_depth, run_samtools_depth
from contig.readiness.table import build_readiness

FIX = Path(__file__).parent / "fixtures" / "readiness"
DEPTH = FIX / "depth.tsv"
PANEL = FIX / "panel.bed"
HOMOLOGY = FIX / "homology.bed"


def _fake_samtools(tmp_path: Path) -> Path:
    fake = tmp_path / "samtools"
    fake.write_text(f"#!/bin/sh\ncat '{DEPTH}'\n")
    fake.chmod(fake.stat().st_mode | 0o111)
    return fake


def test_run_samtools_depth_writes_the_tsv(tmp_path):
    fake = _fake_samtools(tmp_path)
    bam = tmp_path / "sample.bam"
    bam.write_text("")
    out = tmp_path / "depth.tsv"
    result = run_samtools_depth(bam, PANEL, out, samtools_bin=str(fake))
    assert result == out
    depths, stats = load_depth(out)
    assert stats.positions == 150


def test_build_readiness_from_bam_records_the_bam_source(tmp_path):
    fake = _fake_samtools(tmp_path)
    bam = tmp_path / "sample.bam"
    bam.write_text("")
    table = build_readiness(
        bam=bam, bed=PANEL, caveats=HOMOLOGY, samtools_bin=str(fake)
    )
    assert len(table.rows) == 4
    assert {source.kind for source in table.meta.sources} == {"bam", "targets", "caveats"}
    assert any("samtools depth" in (source.note or "") for source in table.meta.sources)


def test_depth_and_bam_are_mutually_exclusive(tmp_path):
    fake = _fake_samtools(tmp_path)
    bam = tmp_path / "sample.bam"
    bam.write_text("")
    with pytest.raises(ValueError, match="exactly one"):
        build_readiness(DEPTH, bam=bam, bed=PANEL, samtools_bin=str(fake))


def test_cli_accepts_a_bam(tmp_path):
    fake = _fake_samtools(tmp_path)
    bam = tmp_path / "sample.bam"
    bam.write_text("")
    out = tmp_path / "readiness.tsv"
    result = CliRunner().invoke(app, [
        "readiness", "--bam", str(bam), "--bed", str(PANEL),
        "--samtools", str(fake), "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert out.read_text().startswith("target\tgene")
