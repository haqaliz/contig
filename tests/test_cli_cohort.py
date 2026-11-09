"""CLI smoke tests for cohort-build/cohort-query."""

import json
from pathlib import Path

from typer.testing import CliRunner

from tests.ansi import plain

from contig.cli import app

FIX = Path(__file__).parent / "fixtures" / "cohort"
VARIANTS = f"{FIX / 'run1.json'},{FIX / 'run2.json'},{FIX / 'run3.json'}"


def _invoke(args):
    return CliRunner().invoke(app, args)


def test_help_lists_options():
    build = _invoke(["cohort-build", "--help"])
    query = _invoke(["cohort-query", "--help"])
    assert build.exit_code == 0 and "--variants" in plain(build.output)
    assert query.exit_code == 0 and "--cohort" in plain(query.output)


def test_build_and_query(tmp_path):
    cohort = tmp_path / "cohort.json"
    built = _invoke(["cohort-build", "--name", "Lab", "--variants", VARIANTS, "--out", str(cohort)])
    assert built.exit_code == 0, built.output
    assert cohort.is_file()

    queried = _invoke(["cohort-query", "--cohort", str(cohort), "--gene", "BRCA1"])
    assert queried.exit_code == 0, queried.output
    assert "BRCA1" in queried.output
    assert "3" in queried.output


def test_build_anonymized(tmp_path):
    cohort = tmp_path / "cohort.json"
    result = _invoke(["cohort-build", "--name", "Lab", "--variants", VARIANTS, "--anonymize", "--out", str(cohort)])
    assert result.exit_code == 0, result.output
    payload = json.loads(cohort.read_text())
    assert payload["meta"]["anonymized"] is True
    assert all(run["path"] == "" for run in payload["meta"]["runs"])


def test_missing_input_exits_nonzero(tmp_path):
    result = _invoke(["cohort-build", "--name", "Lab", "--variants", str(FIX / "missing.json"), "--out", str(tmp_path / "c.json")])
    assert result.exit_code == 1
    assert "not found" in plain(result.output).lower()
