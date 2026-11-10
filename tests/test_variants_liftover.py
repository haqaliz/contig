"""Tests for the Iranome GRCh37 -> GRCh38 chain liftover."""

import csv
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.variants.liftover import lift_iranome, load_chain
from contig.variants.models import VariantKey
from contig.variants.sources import load_iranome

FIX = Path(__file__).parent / "fixtures" / "variants"
CHAIN = FIX / "tiny.chain"

IRANOME = (
    "gene\tchrom\tpos\tref\talt\tallele_freq\tallele_count\tallele_num\n"
    "BRCA1\t1\t101\tA\tG\t0.01\t1\t100\n"
    "BRCA1\t1\t200\tAT\tA\t0.02\t2\t100\n"
    "BRCA1\t1\t201\tA\tG\t0.03\t3\t100\n"
)


def _table(tmp_path: Path) -> Path:
    path = tmp_path / "iranome.tsv"
    path.write_text(IRANOME)
    return path


def test_lifts_snvs_and_skips_gap_spanning_variants(tmp_path):
    out = tmp_path / "iranome_grch38.tsv"
    result = lift_iranome(_table(tmp_path), CHAIN, out)
    assert result["mapped"] == 1
    assert result["unmapped"] == 2
    rows = list(csv.DictReader(out.open(), delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["chrom"] == "1"
    assert rows[0]["pos"] == "201"
    sidecar = json.loads((tmp_path / "iranome_grch38.tsv.lift.json").read_text())
    assert sidecar["source_build"] == "GRCh37"
    assert sidecar["target_build"] == "GRCh38"
    assert sidecar["mapped"] == 1


def test_lifted_table_joins_when_source_build_is_declared(tmp_path):
    out = tmp_path / "iranome_grch38.tsv"
    lift_iranome(_table(tmp_path), CHAIN, out)
    sites = {VariantKey("1", 201, "A", "G")}
    evidence, provenance = load_iranome(
        out, sites, build="GRCh38", source_build="GRCh38"
    )
    assert evidence[sites.pop()].af == 0.01
    assert provenance.build == "GRCh38"
    assert "matched" in (provenance.note or "")


def test_lifted_table_is_skipped_without_the_build_declaration(tmp_path):
    out = tmp_path / "iranome_grch38.tsv"
    lift_iranome(_table(tmp_path), CHAIN, out)
    evidence, provenance = load_iranome(out, {VariantKey("1", 201, "A", "G")}, build="GRCh38")
    assert evidence == {}
    assert "GRCh37" in (provenance.note or "")


def test_reverse_strand_chain_is_refused(tmp_path):
    chain = tmp_path / "reverse.chain"
    chain.write_text(
        "chain 1000 chr1 1000000 - 200 300 chr1 1000000 + 100 200 1\n100\n"
    )
    with pytest.raises(ValueError, match="plus/plus"):
        load_chain(chain)


def test_cli_iranome_lift(tmp_path):
    out = tmp_path / "iranome_grch38.tsv"
    result = CliRunner().invoke(app, [
        "iranome-lift", "--iranome", str(_table(tmp_path)),
        "--chain", str(CHAIN), "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert "1 mapped" in result.output
    assert out.with_name(out.name + ".lift.json").is_file()
