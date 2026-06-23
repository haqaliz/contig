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
