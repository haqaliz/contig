"""Tests for the signed report manifest (Ed25519 over the sidecar)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import SIGNING_KEY_ENV
from contig.cli import app
from contig.reporting.build import (
    build_report,
    check_report,
    check_report_signature,
    signature_path,
    write_report,
)
from contig.reporting.models import ReportSpec
from contig.signing import generate_keypair

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"


def _write(tmp_path: Path) -> tuple[Path, Path, Path | None]:
    html, meta = build_report(RUNS, "r1", ReportSpec(), variants_path=VARIANTS)
    out = tmp_path / "report.html"
    sidecar = tmp_path / "report.json"
    sig = write_report(html, meta, out, sidecar)
    return out, sidecar, sig


def _combined(result) -> str:
    return result.output + getattr(result, "stderr", "")


def test_unsigned_report_has_no_signature_sidecar(tmp_path, monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    _, sidecar, sig = _write(tmp_path)
    assert sig is None
    assert not signature_path(sidecar).exists()
    state = check_report_signature(sidecar)
    assert state["signed"] is False


def test_signed_report_verifies_and_names_the_public_key(tmp_path, monkeypatch):
    private, public = generate_keypair()
    monkeypatch.setenv(SIGNING_KEY_ENV, private)
    _, sidecar, sig = _write(tmp_path)
    assert sig == signature_path(sidecar)
    assert sig.is_file()
    state = check_report_signature(sidecar)
    assert state == {
        "signed": True,
        "ok": True,
        "public_key": public,
        "detail": "",
    }


def test_tampering_with_the_manifest_invalidates_the_signature(tmp_path, monkeypatch):
    private, _ = generate_keypair()
    monkeypatch.setenv(SIGNING_KEY_ENV, private)
    _, sidecar, _ = _write(tmp_path)
    payload = json.loads(sidecar.read_text())
    payload["spec"]["title"] = "tampered"
    sidecar.write_text(json.dumps(payload))
    state = check_report_signature(sidecar)
    assert state["signed"] is True
    assert state["ok"] is False


def test_malformed_signature_sidecar_is_invalid_not_a_crash(tmp_path, monkeypatch):
    private, _ = generate_keypair()
    monkeypatch.setenv(SIGNING_KEY_ENV, private)
    _, sidecar, sig = _write(tmp_path)
    sig.write_text("{not json")
    state = check_report_signature(sidecar)
    assert state["signed"] is True
    assert state["ok"] is False


def test_unsigned_rewrite_removes_a_stale_signature(tmp_path, monkeypatch):
    private, _ = generate_keypair()
    monkeypatch.setenv(SIGNING_KEY_ENV, private)
    _, sidecar, sig = _write(tmp_path)
    assert sig is not None
    monkeypatch.delenv(SIGNING_KEY_ENV)
    _write(tmp_path)
    assert not signature_path(sidecar).exists()


def test_html_tamper_is_caught_by_the_signed_manifest(tmp_path, monkeypatch):
    private, _ = generate_keypair()
    monkeypatch.setenv(SIGNING_KEY_ENV, private)
    out, sidecar, _ = _write(tmp_path)
    out.write_text(out.read_text() + "\n<!-- tampered -->\n")
    html = next(item for item in check_report(sidecar) if item["kind"] == "html")
    assert html["status"] == "stale"
    assert check_report_signature(sidecar)["ok"] is True


def test_report_check_accepts_unsigned_but_require_signature_fails(tmp_path, monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    _, sidecar, _ = _write(tmp_path)
    ok = CliRunner().invoke(app, ["report-check", str(sidecar)])
    assert ok.exit_code == 0, _combined(ok)
    required = CliRunner().invoke(
        app, ["report-check", str(sidecar), "--require-signature"]
    )
    assert required.exit_code == 1
    assert "signed report manifest is required" in _combined(required).lower()


def test_report_check_fails_on_an_invalid_signature(tmp_path, monkeypatch):
    private, _ = generate_keypair()
    monkeypatch.setenv(SIGNING_KEY_ENV, private)
    _, sidecar, _ = _write(tmp_path)
    payload = json.loads(sidecar.read_text())
    payload["run_id"] = "tampered"
    sidecar.write_text(json.dumps(payload))
    result = CliRunner().invoke(app, ["report-check", str(sidecar)])
    assert result.exit_code == 1
    assert "invalid" in _combined(result).lower()
