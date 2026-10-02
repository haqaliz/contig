"""Ed25519 detached signatures over a run record's canonical content (PRD contract E).

These tests run real Ed25519 when `cryptography` is importable; when it is not,
they assert the clear "signing unavailable" path instead, so the suite stays green
on a machine without the optional dependency.
"""

import hashlib

import pytest

from contig.models import (
    ClaimResult,
    ExecutionTarget,
    ReproduceRecord,
    RunRecord,
    TaskEvent,
)
from contig.signing import (
    SigningUnavailableError,
    canonical_bytes_from_raw,
    canonical_record_bytes,
    canonical_sha256,
    canonical_sha256_from_raw,
    generate_keypair,
    signing_available,
    sign_record,
    verify_raw,
    verify_signature,
)


def _record(run_id: str = "r1") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={"reads.fastq.gz": "abc"},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
    )


requires_signing = pytest.mark.skipif(
    not signing_available(), reason="cryptography not installed"
)


def test_canonical_bytes_are_stable_across_calls():
    record = _record()
    assert canonical_record_bytes(record) == canonical_record_bytes(record)


def test_canonical_sha256_is_deterministic():
    assert canonical_sha256(_record()) == canonical_sha256(_record())


def test_canonical_bytes_differ_when_record_content_differs():
    assert canonical_record_bytes(_record("a")) != canonical_record_bytes(_record("b"))


def test_signing_unavailable_raises_clear_error_when_dependency_missing():
    # Only meaningful when cryptography is absent; otherwise the calls succeed and
    # there is nothing to assert here.
    if signing_available():
        pytest.skip("cryptography is installed")
    with pytest.raises(SigningUnavailableError):
        generate_keypair()


@requires_signing
def test_sign_then_verify_round_trips():
    private_key, public_key = generate_keypair()
    record = _record()

    signature = sign_record(record, private_key)

    assert verify_signature(record, signature, public_key) is True


@requires_signing
def test_verify_fails_for_a_tampered_record():
    private_key, public_key = generate_keypair()
    signature = sign_record(_record("original"), private_key)

    tampered = _record("tampered")

    assert verify_signature(tampered, signature, public_key) is False


@requires_signing
def test_verify_fails_for_a_signature_from_a_different_key():
    private_key, _ = generate_keypair()
    _, other_public = generate_keypair()
    record = _record()
    signature = sign_record(record, private_key)

    assert verify_signature(record, signature, other_public) is False


@requires_signing
def test_signature_excludes_itself_so_verification_is_stable():
    # The signature must sign the record content, never a signature field. Signing
    # twice with the same key yields a signature that still verifies the content.
    private_key, public_key = generate_keypair()
    record = _record()
    signature = sign_record(record, private_key)

    assert verify_signature(record, signature, public_key) is True


def _write_signed_old_shape_bundle(dest, record, strip, record_file="run_record.json"):
    """Write a genuinely old-shape record FILE plus a sidecar signed over its own text.

    `strip` mutates the dumped payload dict (deleting the newer key(s), nested where
    applicable). The file text is the stripped JSON; the signature is over
    `canonical_bytes_from_raw` of exactly that text, as an older Contig's signer
    would have produced for it. Returns (public_key, file_text).
    """
    import json as _json

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key, public_key = generate_keypair()
    payload = record.model_dump(mode="json")
    strip(payload)
    text = _json.dumps(payload, indent=2)
    (dest / record_file).write_text(text)
    signature = (
        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key))
        .sign(canonical_bytes_from_raw(text))
        .hex()
    )
    (dest / "signature.json").write_text(
        _json.dumps(
            {
                "algo": "ed25519",
                "public_key": public_key,
                "signature": signature,
                "signed_sha256": canonical_sha256_from_raw(text),
            }
        )
    )
    return public_key, text


# --- history: patch_applied broke pre-field signatures on the MODEL path -------
#
# `RepairStep.patch_applied` is back-compatible for LOADING (a pre-field bundle
# reads as False) but NOT for a signature made before the field existed on the
# model path (`verify_signature`): `canonical_record_bytes` is
# `record.model_dump(mode="json")`, so every
# repair_history entry now carries an extra key the old signed bytes never had.
# Unlike the slice-6/slice-8 breaks this one is NESTED — the added key lives
# inside a list of sub-models, not at the top level — which is why the strip
# below has to recurse and why the break is narrow: a record with an EMPTY
# repair_history serializes byte-identically and its old signature still
# verifies. Both model-path properties stay pinned here (the tests below). The raw
# path (`verify_signature_in_dir`) now verifies such old-shape files -- see the
# flipped pins.


def _record_with_repair_history(run_id: str = "r1") -> RunRecord:
    from contig.models import Diagnosis, Patch, RepairStep

    record = _record(run_id)
    record.repair_history = [
        RepairStep(
            attempt=1,
            diagnosis=Diagnosis(
                failure_class="oom",
                root_cause="Task killed for exceeding its memory allocation.",
                evidence=["exit 137"],
                confidence=0.9,
            ),
            patch=Patch(
                kind="resource",
                operation={"memory_gb": 16},
                rationale="Double the memory and retry.",
                risk="safe",
                expected_signal="task completes",
            ),
            outcome="patched_and_retried",
            patch_applied=True,
        )
    ]
    return record


def _pre_patch_applied_canonical_bytes(record: RunRecord) -> bytes:
    """The canonical bytes this record would have produced before the field.

    Drops exactly `patch_applied`, from every entry of `repair_history` — the
    strip has to reach INTO the list, since that is where the new key lives. The
    rest of the canonicalization (sorted keys, compact separators, UTF-8) is
    copied from `signing.canonical_record_bytes` so the only difference under
    test is the added key.
    """
    import json as _json

    payload = record.model_dump(mode="json")
    old = dict(payload)
    old["repair_history"] = [
        {k: v for k, v in step.items() if k != "patch_applied"}
        for step in payload["repair_history"]
    ]
    # The strip must actually have removed something from every entry, or the
    # test below would pass vacuously over unchanged bytes.
    assert set(payload) == set(old)
    for new_step, old_step in zip(payload["repair_history"], old["repair_history"]):
        assert set(new_step) - set(old_step) == {"patch_applied"}
    return _json.dumps(old, sort_keys=True, separators=(",", ":")).encode("utf-8")


@requires_signing
def test_pre_field_signed_record_file_with_repair_history_still_verifies(tmp_path):
    import json as _json

    from contig.bundle import verify_signature_in_dir

    record = _record_with_repair_history()
    assert record.repair_history  # the nested key needs at least one entry

    def strip(payload):
        for step in payload["repair_history"]:
            del step["patch_applied"]

    _write_signed_old_shape_bundle(tmp_path, record, strip)

    # The stored file is genuinely old-shape: no entry carries patch_applied.
    stored = _json.loads((tmp_path / "run_record.json").read_text())
    assert stored["repair_history"]
    assert all("patch_applied" not in step for step in stored["repair_history"])

    # Verification is over the stored file's own text, so model growth no longer
    # breaks the signature.
    assert verify_signature_in_dir(tmp_path) == {"signed": True, "signature_ok": True}


@requires_signing
def test_pre_field_signature_over_a_record_with_no_repair_history_still_verifies():
    # The narrowing. An empty repair_history has no entry to carry the new key,
    # so the canonical bytes are byte-identical to what an older Contig produced
    # and the old signature is still good. This is the whole basis for calling
    # the break narrow: a clean run's signed bundle is unaffected.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key, public_key = generate_keypair()
    record = _record()
    assert record.repair_history == []

    old_bytes = _pre_patch_applied_canonical_bytes(record)
    assert old_bytes == canonical_record_bytes(record)

    old_signature = (
        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key))
        .sign(old_bytes)
        .hex()
    )

    assert verify_signature(record, old_signature, public_key) is True


# --- widening Patch.kind to add "advisory" is not a signature break -----------
#
# `Patch.kind` grew a seventh Literal member, `"advisory"` (models.py:300), as
# part of the inert-repair-honesty slice. Unlike `patch_applied` (a genuinely
# new key), a `Literal` only constrains what pydantic validates on input -- it
# has no representation of its own in `model_dump(mode="json")`, so an existing
# value like `"env"` must serialize byte-identically whether or not "advisory"
# is also a legal value. Pin that directly, rather than assuming it: a record
# built under an independently-reconstructed OLD (six-member) Literal, carrying
# an "env" patch, produces the exact same canonical bytes as today's code.


def _pre_advisory_literal_canonical_bytes(record: RunRecord) -> bytes:
    """The canonical bytes a pre-advisory-literal Contig would have produced.

    Rebuilds every `repair_history` entry's patch through an independent model
    carrying the OLD six-member `Literal` (no "advisory"), so the comparison
    against today's `canonical_record_bytes` is genuine -- not just re-deriving
    the same code path twice.
    """
    import json as _json
    from typing import Literal as _Literal

    from pydantic import BaseModel as _BaseModel

    class _OldPatch(_BaseModel):
        kind: _Literal["param", "resource", "env", "reference", "retry", "code"]
        operation: dict[str, object]
        rationale: str
        risk: _Literal["safe", "needs_confirmation", "destructive"]
        expected_signal: str

    payload = record.model_dump(mode="json")
    old_steps = []
    for new_step, orig_step in zip(payload["repair_history"], record.repair_history):
        rebuilt = dict(new_step)
        if orig_step.patch is not None:
            rebuilt["patch"] = _OldPatch(**orig_step.patch.model_dump()).model_dump(
                mode="json"
            )
        old_steps.append(rebuilt)
    old_payload = dict(payload)
    old_payload["repair_history"] = old_steps
    return _json.dumps(old_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@requires_signing
def test_pre_advisory_literal_signature_over_an_env_kind_patch_still_verifies():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from contig.models import Patch

    private_key, public_key = generate_keypair()
    record = _record_with_repair_history()
    # "env" existed in the Literal before "advisory" was added -- exactly the
    # value the widening must not disturb.
    record.repair_history[0].patch = Patch(
        kind="env",
        operation={"queue": "long"},
        rationale="Route to a longer-running queue.",
        risk="safe",
        expected_signal="task completes",
    )

    old_bytes = _pre_advisory_literal_canonical_bytes(record)
    assert old_bytes == canonical_record_bytes(record)  # nothing changed

    old_signature = (
        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key))
        .sign(old_bytes)
        .hex()
    )

    assert verify_signature(record, old_signature, public_key) is True


# --- history: known_sites broke pre-slice signatures on the MODEL path -------
#
# `ReferenceIdentity.known_sites` is back-compatible for LOADING (a pre-slice
# bundle reads as None) but NOT for a signature made before the field existed:
# `canonical_record_bytes` is `record.model_dump(mode="json")`, and pydantic emits
# every field, so a nested `"known_sites": null` now appears inside every
# `reference_identity` object. Unlike the `patch_applied` break this one is NOT
# narrow: it does not need a known-sites entry to fire -- any record whose
# `reference_identity` is non-None serializes differently, even one that captured
# no known sites at all. The strip below only has to reach one level down, but it
# applies to every reference-bearing record. The model-path break, its bound (a
# record with no reference identity is byte-identical and still verifies), and the
# honest model-path report (signed, not ok -- never a silent re-sign) stay pinned
# here. The raw path (`verify_signature_in_dir`) now verifies such old-shape
# files -- see the flipped pins.


def _record_with_reference_identity(run_id: str = "r1") -> RunRecord:
    from contig.models import ReferenceIdentity

    record = _record(run_id)
    record.reference_identity = ReferenceIdentity(
        mode="explicit",
        fasta="/refs/genome.fa",
        gtf="/refs/genes.gtf",
    )
    return record


def _pre_known_sites_canonical_bytes(record: RunRecord) -> bytes:
    """The canonical bytes this record would have produced before the field.

    Drops exactly `known_sites`, from the `reference_identity` object -- the new
    key is nested one level down, so the strip reaches into that sub-dict. A
    record with no reference identity has no nested key to drop and serializes
    unchanged. The rest of the canonicalization (sorted keys, compact separators,
    UTF-8) is copied from `signing.canonical_record_bytes` so the only difference
    under test is the added key.
    """
    import json as _json

    payload = record.model_dump(mode="json")
    old = dict(payload)
    identity = payload["reference_identity"]
    if identity is not None:
        old_identity = {k: v for k, v in identity.items() if k != "known_sites"}
        # The strip must actually have removed something, or the tests below would
        # pass vacuously over unchanged bytes.
        assert set(identity) - set(old_identity) == {"known_sites"}
        old["reference_identity"] = old_identity
    return _json.dumps(old, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _strip_known_sites(payload):
    del payload["reference_identity"]["known_sites"]


@requires_signing
def test_pre_slice_signed_bundle_loads_and_still_verifies(tmp_path):
    import json as _json

    from contig.bundle import verify_signature_in_dir

    record = _record_with_reference_identity()
    assert record.reference_identity is not None
    assert record.reference_identity.known_sites is None  # a pre-slice capture

    _write_signed_old_shape_bundle(tmp_path, record, _strip_known_sites)

    stored = _json.loads((tmp_path / "run_record.json").read_text())
    assert "known_sites" not in stored["reference_identity"]

    # Back-compat: the pre-slice JSON still LOADS, with the new field None.
    loaded = RunRecord.model_validate(stored)
    assert loaded.reference_identity is not None
    assert loaded.reference_identity.known_sites is None

    assert verify_signature_in_dir(tmp_path) == {"signed": True, "signature_ok": True}


@requires_signing
def test_pre_slice_signed_bundle_reports_signature_ok_true(tmp_path):
    # The user-visible fate, through the same bundle load and status helper that
    # `contig verify` uses: the pre-slice sidecar is READ and reported ok.
    import json as _json

    from contig.bundle import load_bundle
    from contig.cli import _signature_status

    record = _record_with_reference_identity()
    run_dir = tmp_path / "r1"
    run_dir.mkdir()
    _write_signed_old_shape_bundle(run_dir, record, _strip_known_sites)
    assert "known_sites" not in _json.loads((run_dir / "run_record.json").read_text())[
        "reference_identity"
    ]

    loaded = load_bundle(run_dir)
    assert loaded.reference_identity is not None
    assert loaded.reference_identity.known_sites is None

    assert _signature_status(str(tmp_path), "r1", loaded) == {
        "signed": True,
        "signature_ok": True,
    }


@requires_signing
def test_pre_slice_signed_file_with_tampered_content_still_fails(tmp_path):
    from contig.bundle import verify_signature_in_dir

    _write_signed_old_shape_bundle(
        tmp_path, _record_with_reference_identity(), _strip_known_sites
    )
    path = tmp_path / "run_record.json"
    path.write_text(path.read_text().replace("nf-core/rnaseq", "nf-core/evil"))

    assert verify_signature_in_dir(tmp_path)["signature_ok"] is False


@requires_signing
def test_pre_slice_signature_over_a_record_with_no_reference_identity_still_verifies():
    # The bound of the non-narrow break: with no reference identity there is no
    # nested object to carry the new key, so the canonical bytes are byte-identical
    # to what an older Contig produced and the old signature is still good.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key, public_key = generate_keypair()
    record = _record()
    assert record.reference_identity is None

    old_bytes = _pre_known_sites_canonical_bytes(record)
    assert old_bytes == canonical_record_bytes(record)

    old_signature = (
        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key))
        .sign(old_bytes)
        .hex()
    )

    assert verify_signature(record, old_signature, public_key) is True


# --- Phase 1: canonicalize the stored record JSON, not a re-dumped model --------

def _odd_run_records() -> list[RunRecord]:
    values = [1e16, 1e-7, 0.1 + 0.2, -0.0, 1.5e300, 5e-324, 123456789.123456789]
    out = []
    for i, v in enumerate(values):
        r = _record(f"r{i}")
        r.parameters = {
            "f": v,
            "uni": "caf\u00e9 \u2603 \U0001f9ec",
            "nested": {"a": None, "b": [], "c": {}, "d": [1, 2.0, None, {"z": v}]},
            "empty_list": [],
            "empty_dict": {},
            "quote": 'he said "hi"\n\t\\',
        }
        out.append(r)
    return out


def _odd_reproduce_records() -> list[ReproduceRecord]:
    out = []
    for v in [1e16, 1e-7, 0.1 + 0.2, 0.0, 1.0, 123456789.123456789]:
        out.append(
            ReproduceRecord(
                reproduce_id="rp_1",
                repo="https://example.com/p\u00e4per",
                run_command="python train.py \u2603",
                claims_sha256="a" * 64,
                claim_results=[
                    ClaimResult(
                        id="c1", status="reproduced", claimed=v, observed=v,
                        tolerance=0.02, delta=None, message="caf\u00e9",
                    ),
                    ClaimResult(
                        id="c2", status="reproduced", claimed=v, observed=None,
                        tolerance=1e-7, delta=0.1 + 0.2, message="",
                    ),
                ],
                exit_code=0,
                created_at="2026-07-18T00:00:00Z",
            )
        )
    return out


@pytest.mark.parametrize("record", _odd_run_records() + _odd_reproduce_records())
def test_raw_canonical_bytes_equal_model_canonical_bytes_for_corpus(record):
    raw = record.model_dump_json(indent=2)
    assert canonical_bytes_from_raw(raw) == canonical_record_bytes(record)
    assert canonical_bytes_from_raw(raw.encode("utf-8")) == canonical_record_bytes(record)


def test_canonical_sha256_from_raw_matches_model_sha():
    record = _record()
    raw = record.model_dump_json(indent=2)
    assert canonical_sha256_from_raw(raw) == canonical_sha256(record)
    assert canonical_sha256_from_raw(raw) == hashlib.sha256(
        canonical_record_bytes(record)
    ).hexdigest()


@pytest.mark.parametrize("bad", ["{not json", "", b"\xff\xfe", "[1, 2]", "3", "null", '"s"'])
def test_canonical_bytes_from_raw_rejects_malformed_or_non_object(bad):
    with pytest.raises(ValueError):
        canonical_bytes_from_raw(bad)


@requires_signing
def test_verify_raw_round_trips_and_detects_tamper():
    priv, pub = generate_keypair()
    record = _record()
    sig = sign_record(record, priv)
    raw = record.model_dump_json(indent=2)
    assert verify_raw(raw, sig, pub) is True
    assert verify_raw(raw.replace("r1", "r2"), sig, pub) is False


@requires_signing
def test_verify_raw_rejects_an_added_unknown_field():
    # A field unknown to the model is part of the stored JSON, so tampering with it fails.
    priv, pub = generate_keypair()
    record = _record()
    sig = sign_record(record, priv)
    import json

    data = json.loads(record.model_dump_json())
    data["future_field"] = 1
    assert verify_raw(json.dumps(data), sig, pub) is False


@requires_signing
def test_verify_raw_returns_false_for_malformed_raw_or_signature_or_key():
    priv, pub = generate_keypair()
    record = _record()
    sig = sign_record(record, priv)
    raw = record.model_dump_json(indent=2)
    assert verify_raw("{bad", sig, pub) is False
    assert verify_raw("[1]", sig, pub) is False
    assert verify_raw(raw, "zz", pub) is False
    assert verify_raw(raw, sig, "nothex!!") is False


_DEEP = "[" * 100000 + "]" * 100000


def test_canonical_bytes_from_raw_deep_nesting_raises_value_error():
    with pytest.raises(ValueError):
        canonical_bytes_from_raw(_DEEP)
    with pytest.raises(ValueError):
        canonical_bytes_from_raw('{"a":' + _DEEP + "}")


@requires_signing
def test_verify_raw_deep_nesting_returns_false_never_raises():
    priv, pub = generate_keypair()
    sig = sign_record(_record(), priv)
    assert verify_raw(_DEEP, sig, pub) is False
    assert verify_raw('{"a":' + _DEEP + "}", sig, pub) is False


@requires_signing
def test_verify_raw_returns_false_for_a_valid_but_different_key():
    priv, pub = generate_keypair()
    _, other_pub = generate_keypair()
    record = _record()
    sig = sign_record(record, priv)
    assert verify_raw(record.model_dump_json(indent=2), sig, other_pub) is False


# --- the stored verdict is signed as stored, not recomputed ----------------------


@requires_signing
def test_stored_verdict_current_logic_would_not_compute_still_verifies(tmp_path):
    import json as _json

    from contig.bundle import verify_signature_in_dir

    record = _record()
    current = record.model_dump(mode="json").get("verdict")

    def set_verdict(payload):
        # A verdict value no current logic would compute for this record.
        payload["verdict"] = "pass" if current != "pass" else "fail"

    _write_signed_old_shape_bundle(tmp_path, record, set_verdict)
    stored = _json.loads((tmp_path / "run_record.json").read_text())
    assert stored["verdict"] != current

    assert verify_signature_in_dir(tmp_path) == {"signed": True, "signature_ok": True}

    # Changing the stored verdict afterwards breaks the signature.
    stored["verdict"] = "warn" if stored["verdict"] != "warn" else "fail"
    (tmp_path / "run_record.json").write_text(_json.dumps(stored, indent=2))
    assert verify_signature_in_dir(tmp_path)["signature_ok"] is False


# --- Phase 4c: sign_raw ---------------------------------------------------------

@pytest.mark.skipif(not signing_available(), reason="cryptography not installed")
def test_sign_raw_round_trips_with_verify_raw_and_matches_sign_record():
    from contig.signing import sign_raw

    private_key, public_key = generate_keypair()
    record = _record()
    raw = record.model_dump_json(indent=2)
    sig = sign_raw(raw, private_key)
    assert verify_raw(raw, sig, public_key) is True
    assert sig == sign_record(record, private_key)
    assert verify_raw(raw.replace("r1", "r2"), sig, public_key) is False


@pytest.mark.skipif(not signing_available(), reason="cryptography not installed")
@pytest.mark.parametrize("bad", ["not json", "[1, 2]", b"\xff\xfe"])
def test_sign_raw_rejects_malformed_raw(bad):
    from contig.signing import sign_raw

    private_key, _ = generate_keypair()
    with pytest.raises(ValueError):
        sign_raw(bad, private_key)
