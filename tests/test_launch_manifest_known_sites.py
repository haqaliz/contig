"""Phase 4 of reference known-sites capture: LaunchManifest round-trip.

The three germline known-sites flags (`--dbsnp`/`--known-indels`/`--known-snps`)
must survive on `runs/<id>/launch.json` and be re-fed by `rerun` and `resume`,
exactly like genome/fasta/gtf, so the finalize reference-identity capture is
byte-identical across a re-run. Mirrors the harness in
tests/test_launch_manifest_attendance.py.
"""

import json

from typer.testing import CliRunner

from contig.cli import app
from contig.models import LaunchManifest
from tests.test_known_sites_cli import TRACE_RUN_OK, VARIANT_MQC, _fake_run_executor

runner = CliRunner()

_KNOWN_SITES = (
    ("dbsnp", "d.vcf.gz"),
    ("known_indels", "i.vcf.gz"),
    ("known_snps", "s.vcf.gz"),
)


def _base_manifest_kwargs() -> dict:
    return dict(
        run_id="r1",
        pipeline="nf-core/sarek",
        revision="3.5.1",
        profiles=["test", "docker"],
        backend="local",
        container_runtime="docker",
        created_at="2026-09-10T00:00:00+00:00",
    )


def _run_argv(run_id: str, runs_dir) -> list[str]:
    return [
        "run", "--run-id", run_id, "--runs-dir", str(runs_dir),
        "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
        "--dbsnp", "d.vcf.gz", "--known-indels", "i.vcf.gz",
        "--known-snps", "s.vcf.gz",
    ]


def _spy_known_sites_executor(seen: list):
    def execute(cmd, trace_path):
        seen.append(cmd)
        return _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC)(cmd, trace_path)

    return execute


def _assert_known_sites_in_cmd(cmd: list[str]) -> None:
    for key, value in _KNOWN_SITES:
        flag = f"--{key}"
        assert flag in cmd, f"{flag} missing from rerun argv"
        assert cmd[cmd.index(flag) + 1] == value


def _strip_known_sites_keys(manifest_path) -> None:
    manifest = json.loads(manifest_path.read_text())
    for key in ("dbsnp", "known_indels", "known_snps"):
        manifest.pop(key)
    manifest_path.write_text(json.dumps(manifest))


def test_launch_manifest_round_trips_known_sites():
    # The three fields are real fields that survive a dump/parse round trip.
    manifest = LaunchManifest(
        **_base_manifest_kwargs(),
        dbsnp="d.vcf.gz",
        known_indels="i.vcf.gz",
        known_snps="s.vcf.gz",
    )
    dumped = json.loads(manifest.model_dump_json())
    assert dumped["dbsnp"] == "d.vcf.gz"
    assert dumped["known_indels"] == "i.vcf.gz"
    assert dumped["known_snps"] == "s.vcf.gz"
    round_tripped = LaunchManifest.model_validate_json(manifest.model_dump_json())
    assert round_tripped.dbsnp == "d.vcf.gz"
    assert round_tripped.known_indels == "i.vcf.gz"
    assert round_tripped.known_snps == "s.vcf.gz"


def test_launch_manifest_without_known_sites_keys_validates_to_none():
    # A legacy launch.json (written before these fields existed) must still load.
    legacy_json = json.dumps(
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
    manifest = LaunchManifest.model_validate_json(legacy_json)
    assert manifest.dbsnp is None
    assert manifest.known_indels is None
    assert manifest.known_snps is None


def test_run_with_known_sites_flags_writes_them_to_launch_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC))
    result = runner.invoke(app, _run_argv("ks-manifest", tmp_path))
    assert result.exit_code == 0, result.output
    manifest = json.loads((tmp_path / "ks-manifest" / "launch.json").read_text())
    assert manifest["dbsnp"] == "d.vcf.gz"
    assert manifest["known_indels"] == "i.vcf.gz"
    assert manifest["known_snps"] == "s.vcf.gz"


def test_run_without_known_sites_flags_writes_null_keys_to_launch_manifest(tmp_path, monkeypatch):
    # Pin the unset representation: keys are present with JSON null (the
    # genome/fasta/gtf precedent), not absent.
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "ks-none", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1"],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((tmp_path / "ks-none" / "launch.json").read_text())
    for key in ("dbsnp", "known_indels", "known_snps"):
        assert key in manifest
        assert manifest[key] is None


def test_rerun_re_feeds_known_sites_into_dispatch(tmp_path, monkeypatch):
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_known_sites_executor(seen))
    run_result = runner.invoke(app, _run_argv("ks-orig", tmp_path))
    assert run_result.exit_code == 0, run_result.output

    result = runner.invoke(
        app,
        ["rerun", "ks-orig", "--runs-dir", str(tmp_path), "--new-run-id", "ks-copy"],
    )
    assert result.exit_code == 0, result.output
    _assert_known_sites_in_cmd(seen[-1])
    copy_manifest = json.loads((tmp_path / "ks-copy" / "launch.json").read_text())
    assert copy_manifest["dbsnp"] == "d.vcf.gz"
    assert copy_manifest["known_indels"] == "i.vcf.gz"
    assert copy_manifest["known_snps"] == "s.vcf.gz"


def test_resume_re_feeds_known_sites_into_dispatch(tmp_path, monkeypatch):
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_known_sites_executor(seen))
    run_result = runner.invoke(app, _run_argv("ks-resume", tmp_path))
    assert run_result.exit_code == 0, run_result.output
    (tmp_path / "ks-resume" / "status.json").write_text(
        json.dumps({"run_id": "ks-resume", "state": "cancelled", "pid": 4321,
                    "started_at": "2026-09-10T00:00:00+00:00",
                    "finished_at": "2026-09-10T00:01:00+00:00"})
    )

    result = runner.invoke(app, ["resume", "ks-resume", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    _assert_known_sites_in_cmd(seen[-1])
    manifest = json.loads((tmp_path / "ks-resume" / "launch.json").read_text())
    assert manifest["dbsnp"] == "d.vcf.gz"
    assert manifest["known_indels"] == "i.vcf.gz"
    assert manifest["known_snps"] == "s.vcf.gz"


def test_legacy_manifest_reruns_without_known_sites_params(tmp_path, monkeypatch):
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_known_sites_executor(seen))
    run_result = runner.invoke(app, _run_argv("ks-legacy-rerun", tmp_path))
    assert run_result.exit_code == 0, run_result.output
    _strip_known_sites_keys(tmp_path / "ks-legacy-rerun" / "launch.json")

    result = runner.invoke(
        app,
        ["rerun", "ks-legacy-rerun", "--runs-dir", str(tmp_path), "--new-run-id", "ks-legacy-copy"],
    )
    assert result.exit_code == 0, result.output
    for key, _ in _KNOWN_SITES:
        assert f"--{key}" not in seen[-1]


def test_legacy_manifest_resumes_without_known_sites_params(tmp_path, monkeypatch):
    seen: list = []
    monkeypatch.setattr("contig.cli.default_executor", _spy_known_sites_executor(seen))
    run_result = runner.invoke(app, _run_argv("ks-legacy-resume", tmp_path))
    assert run_result.exit_code == 0, run_result.output
    _strip_known_sites_keys(tmp_path / "ks-legacy-resume" / "launch.json")
    (tmp_path / "ks-legacy-resume" / "status.json").write_text(
        json.dumps({"run_id": "ks-legacy-resume", "state": "cancelled", "pid": 4321,
                    "started_at": "2026-09-10T00:00:00+00:00",
                    "finished_at": "2026-09-10T00:01:00+00:00"})
    )

    result = runner.invoke(app, ["resume", "ks-legacy-resume", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    for key, _ in _KNOWN_SITES:
        assert f"--{key}" not in seen[-1]
