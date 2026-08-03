"""Ed25519 detached signatures over a run record's canonical content (PRD contract E).

These tests run real Ed25519 when `cryptography` is importable; when it is not,
they assert the clear "signing unavailable" path instead, so the suite stays green
on a machine without the optional dependency.
"""

import pytest

from contig.models import ExecutionTarget, RunRecord, TaskEvent
from contig.signing import (
    SigningUnavailableError,
    canonical_record_bytes,
    canonical_sha256,
    generate_keypair,
    signing_available,
    sign_record,
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


# --- disclosed caveat: patch_applied breaks pre-field signatures, narrowly -----
#
# `RepairStep.patch_applied` is back-compatible for LOADING (a pre-field bundle
# reads as False) but NOT for a signature made before the field existed:
# `canonical_record_bytes` is `record.model_dump(mode="json")`, so every
# repair_history entry now carries an extra key the old signed bytes never had.
# Unlike the slice-6/slice-8 breaks this one is NESTED — the added key lives
# inside a list of sub-models, not at the top level — which is why the strip
# below has to recurse and why the break is narrow: a record with an EMPTY
# repair_history serializes byte-identically and its old signature still
# verifies. Both properties are pinned here as KNOWN, not left as surprises.


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
def test_pre_field_signature_over_a_record_with_repair_history_no_longer_verifies():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key, public_key = generate_keypair()
    record = _record_with_repair_history()
    assert record.repair_history  # the break needs at least one entry

    # Sign the bytes an older Contig would have produced for this same record.
    old_signature = (
        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key))
        .sign(_pre_patch_applied_canonical_bytes(record))
        .hex()
    )

    # The extra nested key changes the canonical payload, so the old signature
    # does not verify -- even though nothing about the run itself changed.
    assert verify_signature(record, old_signature, public_key) is False

    # A fresh signature over today's bytes does verify, and differs: the break is
    # the payload shape, not the signing machinery.
    new_signature = sign_record(record, private_key)
    assert verify_signature(record, new_signature, public_key) is True
    assert new_signature != old_signature


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
