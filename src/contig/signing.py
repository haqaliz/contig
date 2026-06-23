"""Ed25519 detached signatures over a run record's canonical content (PRD contract E).

A signed record lets a stranger confirm a RunRecord was produced by the holder of
a given key and has not been altered since. We sign a CANONICAL content hash of the
record (a stable JSON serialization with sorted keys) so the verifier recomputes
exactly the same bytes; the signature signs that content and never itself.

`cryptography` is an optional dependency. When it is not importable we expose a
clear "signing unavailable" path (signing_available() is False, the signing calls
raise SigningUnavailableError) so the rest of the system, and the test suite, keep
working without it. Keys are passed as hex or base64 strings so they travel cleanly
through the CONTIG_SIGNING_KEY env var and a keygen file; they are never logged.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json

from contig.models import RunRecord

try:  # cryptography is optional; degrade to a clear unavailable path without it.
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )

    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only where the dep is absent
    _CRYPTO_AVAILABLE = False


ALGO = "ed25519"


class SigningUnavailableError(RuntimeError):
    """Raised when a signing operation is attempted but `cryptography` is absent."""


def signing_available() -> bool:
    """True when Ed25519 signing is usable (the `cryptography` package imported)."""
    return _CRYPTO_AVAILABLE


def _require_crypto() -> None:
    if not _CRYPTO_AVAILABLE:
        raise SigningUnavailableError(
            "signing requires the 'cryptography' package; install it to sign or verify"
        )


def canonical_record_bytes(record: RunRecord) -> bytes:
    """The exact bytes a signature signs: the record as canonical JSON.

    Pydantic's model_dump_json is rendered key-sorted so the serialization is
    stable regardless of field insertion order, and encoded UTF-8. The record
    carries no signature field, so there is nothing to exclude: the signature can
    never sign itself. The verifier recomputes these same bytes to check a record.
    """
    payload = record.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(record: RunRecord) -> str:
    """The hex SHA-256 of the canonical record bytes (the signed content hash)."""
    return hashlib.sha256(canonical_record_bytes(record)).hexdigest()


def _decode_key(material: str) -> bytes:
    """Decode a key string as hex first, then base64; raise on neither."""
    text = material.strip()
    try:
        return binascii.unhexlify(text)
    except (binascii.Error, ValueError):
        pass
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("key is neither valid hex nor base64") from exc


def generate_keypair() -> tuple[str, str]:
    """Generate an Ed25519 keypair, returned as (private_hex, public_hex).

    Hex strings travel cleanly through env vars and a key file. The private key is
    the 32 byte raw seed; the public key is the 32 byte raw point.
    """
    _require_crypto()
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes_raw()
    public_raw = private.public_key().public_bytes_raw()
    return private_raw.hex(), public_raw.hex()


def public_key_for(private_key: str) -> str:
    """Derive the public key (hex) for a private key string (hex or base64)."""
    _require_crypto()
    private = Ed25519PrivateKey.from_private_bytes(_decode_key(private_key))
    return private.public_key().public_bytes_raw().hex()


def sign_record(record: RunRecord, private_key: str) -> str:
    """Sign a record's canonical content; return the detached signature as hex.

    `private_key` is a hex or base64 Ed25519 private key (e.g. CONTIG_SIGNING_KEY).
    The signature covers canonical_record_bytes(record) and nothing else.
    """
    _require_crypto()
    private = Ed25519PrivateKey.from_private_bytes(_decode_key(private_key))
    signature = private.sign(canonical_record_bytes(record))
    return signature.hex()


def verify_signature(record: RunRecord, signature: str, public_key: str) -> bool:
    """True iff `signature` (hex) is a valid Ed25519 signature of `record` by `public_key`.

    A tampered record, a wrong key, or a malformed signature all return False
    rather than raising, so callers get a clean boolean verdict.
    """
    _require_crypto()
    try:
        public = Ed25519PublicKey.from_public_bytes(_decode_key(public_key))
        public.verify(bytes.fromhex(signature), canonical_record_bytes(record))
        return True
    except (InvalidSignature, ValueError):
        return False
