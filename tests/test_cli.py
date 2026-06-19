from typer.testing import CliRunner

from contig.cli import app

runner = CliRunner()


def test_version_prints_package_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.0.1" in result.output


def test_plan_shows_default_pipeline():
    result = runner.invoke(app, ["plan", "--work-dir", "/tmp/run"])
    assert result.exit_code == 0
    assert "nf-core/rnaseq" in result.output


def test_plan_mentions_chosen_backend():
    result = runner.invoke(app, ["plan", "--work-dir", "/tmp/run", "--backend", "slurm"])
    assert result.exit_code == 0
    assert "slurm" in result.output


def test_plan_rejects_invalid_backend():
    result = runner.invoke(app, ["plan", "--work-dir", "/tmp/run", "--backend", "bogus"])
    assert result.exit_code != 0


def test_plan_echoes_custom_pipeline():
    result = runner.invoke(
        app, ["plan", "--work-dir", "/tmp/run", "--pipeline", "nf-core/sarek"]
    )
    assert result.exit_code == 0
    assert "nf-core/sarek" in result.output
