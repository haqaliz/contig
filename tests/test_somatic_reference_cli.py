"""Somatic reference wiring (C4-1): Mutect2 PON / germline-resource flags.

sarek accepts `--pon`/`--pon_tbi`/`--germline_resource`/`--germline_resource_tbi`
for a real Mutect2 somatic run. These typed flags must reach `params` (and so the
Nextflow argv), be refused pre-launch when a supplied path is missing/unreadable
or a `.tbi` is supplied without its main file, and be replayed by `rerun`/`resume`
via `launch.json`, exactly like the germline known-sites flags.

Harness mirrors tests/test_launch_manifest_known_sites.py.
"""

import json
import os

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.models import LaunchManifest
from tests.test_known_sites_cli import TRACE_RUN_OK, VARIANT_MQC, _fake_run_executor

runner = CliRunner()

_SOMATIC = (
    ("pon", "--pon"),
    ("pon_tbi", "--pon-tbi"),
    ("germline_resource", "--germline-resource"),
    ("germline_resource_tbi", "--germline-resource-tbi"),
)


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return path


def _reference_files(tmp_path):
    """Four real paths, so the pre-flight existence/readability gate passes."""
    return {
        "pon": _touch(tmp_path / "refs" / "pon.vcf.gz"),
        "pon_tbi": _touch(tmp_path / "refs" / "pon.vcf.gz.tbi"),
        "germline_resource": _touch(tmp_path / "refs" / "germline.vcf.gz"),
        "germline_resource_tbi": _touch(tmp_path / "refs" / "germline.vcf.gz.tbi"),
    }


def _run_argv(run_id, runs_dir, refs):
    return [
        "run", "--run-id", run_id, "--runs-dir", str(runs_dir),
        "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
        "--assay", "somatic_variant_calling",
        "--pon", str(refs["pon"]), "--pon-tbi", str(refs["pon_tbi"]),
        "--germline-resource", str(refs["germline_resource"]),
        "--germline-resource-tbi", str(refs["germline_resource_tbi"]),
    ]


def _spy_executor(seen):
    def execute(cmd, trace_path):
        seen.append(cmd)
        return _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC)(cmd, trace_path)

    return execute


def _assert_reference_in_cmd(cmd, refs):
    for key, _flag in _SOMATIC:
        # Nextflow params carry sarek's own underscore names (--pon_tbi), not
        # Contig's dashed CLI spelling.
        flag = f"--{key}"
        assert flag in cmd, f"{flag} missing from argv"
        assert cmd[cmd.index(flag) + 1] == str(refs[key])


def test_launch_manifest_round_trips_somatic_references(tmp_path):
    refs = {key: str(value) for key, value in _reference_files(tmp_path).items()}
    manifest = LaunchManifest(
        run_id="r1",
        pipeline="nf-core/sarek",
        revision="3.5.1",
        profiles=["test", "docker"],
        backend="local",
        container_runtime="docker",
        created_at="2026-10-21T00:00:00+00:00",
        **refs,
    )

    dumped = json.loads(manifest.model_dump_json())
    for key, _flag in _SOMATIC:
        assert dumped[key] == refs[key]
    round_tripped = LaunchManifest.model_validate_json(manifest.model_dump_json())
    for key, _flag in _SOMATIC:
        assert getattr(round_tripped, key) == refs[key]


def test_legacy_manifest_without_somatic_references_validates_to_none():
    legacy = json.dumps(
        {
            "run_id": "legacy",
            "pipeline": "nf-core/sarek",
            "revision": "3.5.1",
            "profiles": ["docker"],
            "backend": "local",
            "container_runtime": "docker",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )

    manifest = LaunchManifest.model_validate_json(legacy)

    for key, _flag in _SOMATIC:
        assert getattr(manifest, key) is None


def test_run_somatic_reference_flags_land_in_params_and_argv(tmp_path, monkeypatch):
    refs = _reference_files(tmp_path)
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_executor(seen))

    result = runner.invoke(app, _run_argv("pon-run", tmp_path, refs))

    assert result.exit_code == 0, result.output
    manifest = json.loads((tmp_path / "pon-run" / "launch.json").read_text())
    for key, _flag in _SOMATIC:
        assert manifest[key] == str(refs[key])
    _assert_reference_in_cmd(seen[-1], refs)


def test_run_refuses_missing_pon_path_before_launch(tmp_path, monkeypatch):
    refs = _reference_files(tmp_path)
    missing = tmp_path / "refs" / "nope.vcf.gz"
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_executor(seen))

    result = runner.invoke(
        app,
        ["run", "--run-id", "pon-missing", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling",
         "--pon", str(missing), "--pon-tbi", str(refs["pon_tbi"])],
    )

    assert result.exit_code != 0
    assert str(missing) in result.output
    assert seen == []  # refused pre-launch
    assert not (tmp_path / "pon-missing" / "launch.json").exists()


def test_run_refuses_unreadable_pon_path_before_launch(tmp_path, monkeypatch):
    if os.geteuid() == 0:
        pytest.skip("root can read a chmod-000 file")
    refs = _reference_files(tmp_path)
    refs["pon"].chmod(0)
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_executor(seen))

    result = runner.invoke(app, _run_argv("pon-unreadable", tmp_path, refs))

    assert result.exit_code != 0
    assert str(refs["pon"]) in result.output
    assert seen == []
    assert not (tmp_path / "pon-unreadable" / "launch.json").exists()


def test_run_refuses_pon_without_its_tbi(tmp_path, monkeypatch):
    refs = _reference_files(tmp_path)
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_executor(seen))

    result = runner.invoke(
        app,
        ["run", "--run-id", "pon-no-tbi", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling", "--pon", str(refs["pon"])],
    )

    assert result.exit_code != 0
    assert "--pon-tbi" in result.output
    assert seen == []
    assert not (tmp_path / "pon-no-tbi" / "launch.json").exists()


def test_run_refuses_tbi_without_its_main_file(tmp_path, monkeypatch):
    refs = _reference_files(tmp_path)
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_executor(seen))

    result = runner.invoke(
        app,
        ["run", "--run-id", "tbi-only", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling", "--pon-tbi", str(refs["pon_tbi"])],
    )

    assert result.exit_code != 0
    assert "--pon" in result.output
    assert seen == []


def test_run_refuses_somatic_reference_flags_on_germline_assay(tmp_path, monkeypatch):
    refs = _reference_files(tmp_path)
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_executor(seen))

    result = runner.invoke(
        app,
        ["run", "--run-id", "pon-germline", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--pon", str(refs["pon"]), "--pon-tbi", str(refs["pon_tbi"])],
    )

    assert result.exit_code != 0
    assert "only valid for the somatic_variant_calling assay" in result.output
    assert "variant_calling" in result.output
    assert seen == []
    assert not (tmp_path / "pon-germline" / "launch.json").exists()


def test_rerun_replays_somatic_references(tmp_path, monkeypatch):
    refs = _reference_files(tmp_path)
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_executor(seen))
    assert runner.invoke(app, _run_argv("pon-orig", tmp_path, refs)).exit_code == 0

    result = runner.invoke(
        app,
        ["rerun", "pon-orig", "--runs-dir", str(tmp_path), "--new-run-id", "pon-copy"],
    )

    assert result.exit_code == 0, result.output
    _assert_reference_in_cmd(seen[-1], refs)
    copy_manifest = json.loads((tmp_path / "pon-copy" / "launch.json").read_text())
    for key, _flag in _SOMATIC:
        assert copy_manifest[key] == str(refs[key])


def test_resume_replays_somatic_references(tmp_path, monkeypatch):
    refs = _reference_files(tmp_path)
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_executor(seen))
    assert runner.invoke(app, _run_argv("pon-resume", tmp_path, refs)).exit_code == 0
    (tmp_path / "pon-resume" / "status.json").write_text(
        json.dumps({"run_id": "pon-resume", "state": "cancelled", "pid": 4321,
                    "started_at": "2026-10-21T00:00:00+00:00",
                    "finished_at": "2026-10-21T00:01:00+00:00"})
    )

    result = runner.invoke(app, ["resume", "pon-resume", "--runs-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    _assert_reference_in_cmd(seen[-1], refs)
    manifest = json.loads((tmp_path / "pon-resume" / "launch.json").read_text())
    for key, _flag in _SOMATIC:
        assert manifest[key] == str(refs[key])
