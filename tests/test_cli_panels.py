"""CLI smoke tests for the panel builder and registry."""

from pathlib import Path

from typer.testing import CliRunner

from contig.cli import app

FIX = Path(__file__).parent / "fixtures" / "panels"
GTF = str(FIX / "genes.gtf")
HGNC = str(FIX / "hgnc.tsv")
BED = str(FIX / "panel.bed")


def _invoke(args):
    return CliRunner().invoke(app, args)


def test_panel_build_help_lists_options():
    result = _invoke(["panel-build", "--help"])
    assert result.exit_code == 0
    assert "--genes" in result.output
    assert "--bed" in result.output
    assert "--gtf" in result.output


def test_build_from_genes_list_and_show(tmp_path):
    out = tmp_path / "panels"
    built = _invoke([
        "panel-build", "--name", "Hereditary cancer", "--genes", "BRCA1,BRCA2",
        "--gtf", GTF, "--hgnc", HGNC, "--out-dir", str(out),
    ])
    assert built.exit_code == 0, built.output
    panel_id = built.output.splitlines()[0].split(" ", 1)[1]
    assert (out / f"{panel_id}.bed").is_file()

    listed = _invoke(["panel-list", "--dir", str(out)])
    assert listed.exit_code == 0
    assert panel_id in listed.output
    assert "Hereditary cancer" in listed.output

    shown = _invoke(["panel-show", panel_id, "--dir", str(out)])
    assert shown.exit_code == 0
    assert '"genes"' in shown.output
    assert "BRCA1" in shown.output


def test_version_label_is_listed(tmp_path):
    out = tmp_path / "panels"
    built = _invoke([
        "panel-build", "--name", "Versioned", "--genes", "BRCA1",
        "--gtf", GTF, "--hgnc", HGNC, "--version", "2", "--out-dir", str(out),
    ])
    assert built.exit_code == 0, built.output
    listed = _invoke(["panel-list", "--dir", str(out)])
    assert "\t2\t" in listed.output


def test_build_from_bed(tmp_path):
    out = tmp_path / "panels"
    result = _invoke(["panel-build", "--name", "Existing", "--bed", BED, "--out-dir", str(out)])
    assert result.exit_code == 0, result.output
    assert list(out.glob("*.bed"))


def test_unknown_gene_exits_nonzero(tmp_path):
    result = _invoke([
        "panel-build", "--name", "Bad", "--genes", "NOTAGENE",
        "--gtf", GTF, "--hgnc", HGNC, "--out-dir", str(tmp_path),
    ])
    assert result.exit_code == 1
    assert "unknown HGNC" in result.output


def test_genes_and_bed_are_mutually_exclusive(tmp_path):
    result = _invoke([
        "panel-build", "--name", "Bad", "--genes", "BRCA1", "--bed", BED,
        "--out-dir", str(tmp_path),
    ])
    assert result.exit_code == 1
    assert "exactly one" in result.output
