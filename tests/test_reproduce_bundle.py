"""Tests for the signed reproduce bundle (C8 slice 1, Phase 3).

Mirrors tests/test_bundle.py's conventions: no conftest, tmp_path, monkeypatch
for the signing key env var. The load-bearing assertion is that
`_maybe_write_signature` (imported unchanged from contig.bundle) signs a
`ReproduceRecord` exactly as it signs a `RunRecord` -- its type hint says
`RunRecord` but that is not runtime-enforced.
"""

import json

import pytest

from contig.bundle import _maybe_write_signature, load_reproduction, write_reproduce_bundle
from contig.models import ClaimResult, ReproduceRecord
from contig.signing import canonical_sha256, generate_keypair, signing_available, verify_signature

requires_signing = pytest.mark.skipif(
    not signing_available(), reason="cryptography not installed"
)


def _claim(id_="c1", status="reproduced", claimed=0.9, observed=0.9, tolerance=0.02, delta=0.0):
    return ClaimResult(
        id=id_,
        status=status,
        claimed=claimed,
        observed=observed,
        tolerance=tolerance,
        delta=delta,
        message="ok",
    )


def _record() -> ReproduceRecord:
    return ReproduceRecord(
        reproduce_id="rp_1",
        repo="https://github.com/example/paper",
        run_command="python train.py --seed 0",
        claims_sha256="a" * 64,
        claim_results=[_claim()],
        exit_code=0,
        created_at="2026-07-18T00:00:00Z",
        interpreter="cpython-3.12",
        tool="contig",
    )


# --- _maybe_write_signature signs a ReproduceRecord unchanged -------------------


@requires_signing
def test_maybe_write_signature_signs_a_reproduce_record(tmp_path, monkeypatch):
    private_key, public_key = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)
    record = _record()

    _maybe_write_signature(record, tmp_path)

    sidecar_path = tmp_path / "signature.json"
    assert sidecar_path.is_file()
    sidecar = json.loads(sidecar_path.read_text())
    assert sidecar["algo"] == "ed25519"
    assert sidecar["public_key"] == public_key
    assert sidecar["signed_sha256"] == canonical_sha256(record)
    assert verify_signature(record, sidecar["signature"], sidecar["public_key"]) is True


@requires_signing
def test_maybe_write_signature_verification_fails_for_tampered_reproduce_record(
    tmp_path, monkeypatch
):
    private_key, public_key = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)
    record = _record()

    _maybe_write_signature(record, tmp_path)

    sidecar = json.loads((tmp_path / "signature.json").read_text())
    tampered = record.model_copy(update={"exit_code": 1})
    assert verify_signature(tampered, sidecar["signature"], sidecar["public_key"]) is False


# --- write_reproduce_bundle ------------------------------------------------------


def test_write_reproduce_bundle_writes_record_and_manifest_without_signing_key(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("CONTIG_SIGNING_KEY", raising=False)
    record = _record()

    json_path = write_reproduce_bundle(record, tmp_path)

    assert json_path == tmp_path / "reproduce_record.json"
    assert json_path.is_file()
    assert (tmp_path / "reproduce.json").is_file()
    assert not (tmp_path / "signature.json").exists()


@requires_signing
def test_write_reproduce_bundle_writes_signature_sidecar_when_key_is_set(tmp_path, monkeypatch):
    private_key, public_key = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)
    record = _record()

    write_reproduce_bundle(record, tmp_path)

    sidecar = json.loads((tmp_path / "signature.json").read_text())
    assert sidecar["public_key"] == public_key
    assert verify_signature(record, sidecar["signature"], sidecar["public_key"]) is True


def test_write_reproduce_bundle_creates_missing_dest_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTIG_SIGNING_KEY", raising=False)
    nested = tmp_path / "does" / "not" / "exist"
    assert not nested.exists()

    json_path = write_reproduce_bundle(_record(), nested)

    assert json_path.is_file()
    assert json_path.parent == nested


def test_reproduce_manifest_carries_rerun_fields(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTIG_SIGNING_KEY", raising=False)
    record = _record()

    write_reproduce_bundle(record, tmp_path)

    manifest = json.loads((tmp_path / "reproduce.json").read_text())
    assert manifest["reproduce_id"] == record.reproduce_id
    assert manifest["repo"] == record.repo
    assert manifest["run_command"] == record.run_command
    assert manifest["claims_sha256"] == record.claims_sha256
    assert manifest["created_at"] == record.created_at


# --- load_reproduction -----------------------------------------------------------


def test_load_reproduction_round_trips_a_written_record(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTIG_SIGNING_KEY", raising=False)
    original = _record()

    json_path = write_reproduce_bundle(original, tmp_path)

    loaded = load_reproduction(json_path.parent)
    assert loaded == original


def test_load_reproduction_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_reproduction(tmp_path)
