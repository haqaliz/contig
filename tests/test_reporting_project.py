"""Tests for project manifests and batch report/check."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.reporting.project import load_project

FIX = Path(__file__).parent / "fixtures" / "reporting"


def _project(tmp_path: Path, *, bundle: bool = False, extra: dict | None = None) -> Path:
    shutil.copytree(FIX / "runs", tmp_path / "runs")
    shutil.copyfile(FIX / "variants.json", tmp_path / "variants.json")
    shutil.copyfile(FIX / "readiness.json", tmp_path / "readiness.json")
    shutil.copyfile(FIX / "spec.json", tmp_path / "spec.json")
    entries = [
        {
            "id": "one",
            "run_id": "r1",
            "variants": "variants.json",
            "readiness": "readiness.json",
            "spec": "spec.json",
            "bundle": bundle,
        },
        {
            "id": "two",
            "run_id": "r1",
            "variants": "variants.json",
            "template": "internal",
        },
    ]
    if extra:
        entries.append(extra)
    manifest = tmp_path / "project.json"
    manifest.write_text(json.dumps({
        "name": "Test project",
        "out_dir": "reports",
        "reports": entries,
    }))
    return manifest


def test_batch_builds_every_report_and_checks_current(tmp_path):
    manifest = _project(tmp_path)
    built = CliRunner().invoke(
        app, ["report-batch", "--project", str(manifest), "--check"]
    )
    assert built.exit_code == 0, built.output
    for name in ("one.html", "one.json", "two.html", "two.json"):
        assert (tmp_path / "reports" / name).is_file(), name
    checked = CliRunner().invoke(
        app, ["report-check-batch", "--project", str(manifest)]
    )
    assert checked.exit_code == 0, checked.output
    assert "current one" in checked.output
    assert "current two" in checked.output


def test_batch_check_fails_after_tampering(tmp_path):
    manifest = _project(tmp_path)
    assert CliRunner().invoke(
        app, ["report-batch", "--project", str(manifest)]
    ).exit_code == 0
    (tmp_path / "reports/one.html").write_text("tampered")
    checked = CliRunner().invoke(
        app, ["report-check-batch", "--project", str(manifest)]
    )
    assert checked.exit_code == 1
    assert "NOT CURRENT one" in checked.output


def test_relative_paths_resolve_from_the_manifest_dir(tmp_path, monkeypatch):
    manifest = _project(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    built = CliRunner().invoke(app, ["report-batch", "--project", str(manifest)])
    assert built.exit_code == 0, built.output
    assert (tmp_path / "reports/one.html").is_file()


def test_bundle_flag_writes_a_portable_bundle(tmp_path):
    manifest = _project(tmp_path, bundle=True)
    built = CliRunner().invoke(app, ["report-batch", "--project", str(manifest)])
    assert built.exit_code == 0, built.output
    assert (tmp_path / "reports/one/report.html").is_file()
    assert (tmp_path / "reports/one/tables/variants.json").is_file()


def test_one_failure_does_not_stop_the_others(tmp_path):
    manifest = _project(tmp_path, extra={"id": "broken", "run_id": "missing"})
    built = CliRunner().invoke(app, ["report-batch", "--project", str(manifest)])
    assert built.exit_code == 1
    assert "FAILED broken" in built.output
    assert (tmp_path / "reports/one.html").is_file()
    assert (tmp_path / "reports/two.html").is_file()


def test_duplicate_ids_are_refused(tmp_path):
    manifest = tmp_path / "project.json"
    manifest.write_text(json.dumps({
        "reports": [
            {"id": "same", "run_id": "r1"},
            {"id": "same", "run_id": "r2"},
        ]
    }))
    with pytest.raises(ValueError, match="duplicate"):
        load_project(manifest)
