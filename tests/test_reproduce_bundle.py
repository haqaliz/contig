"""Tests for the signed reproduce bundle (C8 slice 1, Phase 3).

Mirrors tests/test_bundle.py's conventions: no conftest, tmp_path, monkeypatch
for the signing key env var. The load-bearing assertion is that
`_maybe_write_signature` (imported unchanged from contig.bundle) signs a
`ReproduceRecord` exactly as it signs a `RunRecord` -- its type hint says
`RunRecord` but that is not runtime-enforced.
"""

import json

import pytest

from contig.bundle import (
    _maybe_write_signature,
    load_reproduction,
    verify_signature_in_dir,
    write_reproduce_bundle,
)
from contig.models import ClaimResult, Diagnosis, Patch, RepairStep, ReproduceRecord
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


# --- repair_history survives the bundle round-trip (C8 slice 2, Task 4) --------


def _healed_record() -> ReproduceRecord:
    record = _record()
    return record.model_copy(
        update={
            "repair_history": [
                RepairStep(
                    attempt=1,
                    diagnosis=Diagnosis(
                        failure_class="missing_dependency",
                        root_cause="missing Python module 'numpy'",
                        evidence=["ModuleNotFoundError: No module named 'numpy'"],
                        confidence=0.8,
                    ),
                    patch=Patch(
                        kind="env",
                        operation={"install": "numpy"},
                        rationale="install numpy and retry",
                        risk="needs_confirmation",
                        expected_signal="run exits 0 after install",
                    ),
                    outcome="installed_and_retried",
                    detail="installed numpy; retry exited 0",
                )
            ]
        }
    )


def test_healed_record_repair_history_round_trips_through_the_bundle(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTIG_SIGNING_KEY", raising=False)
    original = _healed_record()

    json_path = write_reproduce_bundle(original, tmp_path)

    loaded = load_reproduction(json_path.parent)
    assert loaded == original
    assert len(loaded.repair_history) == 1
    assert loaded.repair_history[0].outcome == "installed_and_retried"
    assert loaded.repair_history[0].patch.operation == {"install": "numpy"}


@requires_signing
def test_healed_record_signature_verifies(tmp_path, monkeypatch):
    private_key, public_key = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)
    record = _healed_record()

    write_reproduce_bundle(record, tmp_path)

    sidecar = json.loads((tmp_path / "signature.json").read_text())
    assert sidecar["public_key"] == public_key
    assert verify_signature(record, sidecar["signature"], sidecar["public_key"]) is True


def test_bundle_json_without_repair_history_still_loads_as_empty_list(tmp_path):
    # Legacy bundle written before repair_history existed: no key in the JSON.
    legacy_json = {
        "reproduce_id": "rp_legacy",
        "repo": "https://github.com/example/paper",
        "run_command": "python train.py --seed 0",
        "claims_sha256": "a" * 64,
        "claim_results": [],
        "exit_code": 0,
        "created_at": "2026-07-18T00:00:00Z",
        "interpreter": "cpython-3.12",
        "tool": "contig",
    }
    (tmp_path / "reproduce_record.json").write_text(json.dumps(legacy_json))

    loaded = load_reproduction(tmp_path)
    assert loaded.repair_history == []


# --- source_url / source_commit survive the bundle round-trip (Task 4) --------


def _remote_record() -> ReproduceRecord:
    record = _record()
    return record.model_copy(
        update={
            "source_url": "https://github.com/example/paper.git",
            "source_commit": "a" * 40,
        }
    )


def test_remote_record_source_fields_round_trip_through_the_bundle(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTIG_SIGNING_KEY", raising=False)
    original = _remote_record()

    json_path = write_reproduce_bundle(original, tmp_path)

    loaded = load_reproduction(json_path.parent)
    assert loaded == original
    assert loaded.source_url == "https://github.com/example/paper.git"
    assert loaded.source_commit == "a" * 40


def test_reproduce_manifest_carries_source_url_and_commit(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTIG_SIGNING_KEY", raising=False)
    record = _remote_record()

    write_reproduce_bundle(record, tmp_path)

    manifest = json.loads((tmp_path / "reproduce.json").read_text())
    assert manifest["source_url"] == record.source_url
    assert manifest["source_commit"] == record.source_commit


def test_reproduce_manifest_carries_null_source_fields_for_a_local_run(tmp_path, monkeypatch):
    # Unconditional keys: always present, null for a local run -- a consumer can
    # always do manifest["source_commit"] without a KeyError/.get() dance.
    monkeypatch.delenv("CONTIG_SIGNING_KEY", raising=False)
    record = _record()
    assert record.source_url is None
    assert record.source_commit is None

    write_reproduce_bundle(record, tmp_path)

    manifest = json.loads((tmp_path / "reproduce.json").read_text())
    assert manifest["source_url"] is None
    assert manifest["source_commit"] is None


def test_local_record_source_fields_default_to_none_on_round_trip(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTIG_SIGNING_KEY", raising=False)
    original = _record()

    json_path = write_reproduce_bundle(original, tmp_path)

    loaded = load_reproduction(json_path.parent)
    assert loaded == original
    assert loaded.source_url is None
    assert loaded.source_commit is None


def test_bundle_json_without_source_fields_still_loads_as_none(tmp_path):
    # Pre-slice bundle: neither key exists in the JSON at all.
    legacy_json = {
        "reproduce_id": "rp_legacy",
        "repo": "https://github.com/example/paper",
        "run_command": "python train.py --seed 0",
        "claims_sha256": "a" * 64,
        "claim_results": [],
        "exit_code": 0,
        "created_at": "2026-07-18T00:00:00Z",
        "interpreter": "cpython-3.12",
        "tool": "contig",
    }
    (tmp_path / "reproduce_record.json").write_text(json.dumps(legacy_json))

    loaded = load_reproduction(tmp_path)
    assert loaded.source_url is None
    assert loaded.source_commit is None


# --- a pre-slice-6 SIGNED bundle still verifies --------------------------------
#
# Adding source_url/source_commit is back-compatible for LOADING and, since
# verification runs over the stored record FILE's own text (not a re-dumped
# model), for a signature made before the fields existed too. The fixture is a
# genuinely old-shape file: the two keys are deleted from the stored JSON, and
# the signature is over canonical_bytes_from_raw of that exact text.


def _write_signed_old_shape_reproduce_bundle(dest, record, drop):
    """Write an old-shape reproduce_record.json (keys in `drop` deleted from the
    stored text) plus a sidecar signed over `canonical_bytes_from_raw` of that text."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from contig.signing import canonical_bytes_from_raw, canonical_sha256_from_raw

    private_key, public_key = generate_keypair()
    payload = record.model_dump(mode="json")
    for key in drop:
        del payload[key]
    text = json.dumps(payload, indent=2)
    (dest / "reproduce_record.json").write_text(text)
    signature = (
        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key))
        .sign(canonical_bytes_from_raw(text))
        .hex()
    )
    (dest / "signature.json").write_text(
        json.dumps(
            {
                "algo": "ed25519",
                "public_key": public_key,
                "signature": signature,
                "signed_sha256": canonical_sha256_from_raw(text),
            }
        )
    )
    return text


@requires_signing
def test_pre_slice_6_signed_record_file_without_source_fields_still_verifies(tmp_path):
    record = _record()  # a local run: both new fields are None
    assert record.source_url is None and record.source_commit is None

    text = _write_signed_old_shape_reproduce_bundle(
        tmp_path, record, ("source_url", "source_commit")
    )
    stored = json.loads(text)
    assert "source_url" not in stored and "source_commit" not in stored

    result = verify_signature_in_dir(tmp_path, record_file="reproduce_record.json")
    assert result == {"signed": True, "signature_ok": True}

    # Tampering with the stored file still breaks it.
    stored["run_command"] = "evil"
    (tmp_path / "reproduce_record.json").write_text(json.dumps(stored, indent=2))
    assert (
        verify_signature_in_dir(tmp_path, record_file="reproduce_record.json")[
            "signature_ok"
        ]
        is False
    )


# --- verify_signature_in_dir over a reproduce bundle ----------------------------


@requires_signing
def test_verify_in_dir_valid_reproduce_bundle(tmp_path, monkeypatch):
    private_key, _ = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)
    write_reproduce_bundle(_record(), tmp_path)

    result = verify_signature_in_dir(tmp_path, record_file="reproduce_record.json")

    assert result == {"signed": True, "signature_ok": True}


@requires_signing
def test_verify_in_dir_tampered_reproduce_bundle_fails(tmp_path, monkeypatch):
    private_key, _ = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)
    write_reproduce_bundle(_record(), tmp_path)
    path = tmp_path / "reproduce_record.json"
    data = json.loads(path.read_text())
    data["exit_code"] = 1
    path.write_text(json.dumps(data, indent=2))

    result = verify_signature_in_dir(tmp_path, record_file="reproduce_record.json")

    assert result == {"signed": True, "signature_ok": False}


# --- Phase 4c: sign what is stored ---------------------------------------------


def _record_with_claim(value) -> ReproduceRecord:
    rec = _record()
    rec.claim_results = [_claim(claimed=value)]
    return rec


@requires_signing
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_claim_bundle_verifies_raw(tmp_path, monkeypatch, value):
    private_key, _ = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)

    write_reproduce_bundle(_record_with_claim(value), tmp_path)

    result = verify_signature_in_dir(tmp_path, record_file="reproduce_record.json")
    assert result.get("signature_ok") is True
    assert "signature_detail" not in result


@requires_signing
def test_non_finite_claim_stored_as_null_and_verifies(tmp_path, monkeypatch):
    private_key, _ = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)

    write_reproduce_bundle(_record_with_claim(float("inf")), tmp_path)

    stored = json.loads((tmp_path / "reproduce_record.json").read_text())
    assert stored["claim_results"][0]["claimed"] is None
    assert verify_signature_in_dir(tmp_path, record_file="reproduce_record.json")[
        "signature_ok"
    ] is True


@requires_signing
def test_finite_records_sign_byte_identically_to_the_model_path(tmp_path, monkeypatch):
    from contig.bundle import write_bundle
    from contig.signing import sign_record
    from tests.test_signing import _odd_reproduce_records, _odd_run_records

    private_key, _ = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)

    for i, record in enumerate(_odd_run_records() + _odd_reproduce_records()):
        d = tmp_path / str(i)
        if isinstance(record, ReproduceRecord):
            write_reproduce_bundle(record, d)
        else:
            write_bundle(record, d)
        sidecar = json.loads((d / "signature.json").read_text())
        assert sidecar["signature"] == sign_record(record, private_key)
        assert sidecar["signed_sha256"] == canonical_sha256(record)
