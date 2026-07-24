"""Tests for the checkout-tree digest helper (C8 slice 8, Phase 1) and the
signed record field + manifest echo + back-compat + disclosed break (Phase 2).

`compute_tree_sha256` is a pure, stdlib-only helper: no git, no network. All
fixture trees here are built directly on disk under `tmp_path`. The published
algorithm (walk with `os.walk(followlinks=False)`, prune `.git` dirs and
symlinked dirs, fold sorted `f"{relpath}\\0{hexdigest}\\n"` lines, sha256 the
UTF-8 blob) is pinned by test 10 so the CHANGELOG spec stays honest.

Phase 2 adds `ReproduceRecord.source_tree_sha256` (signed, additive, defaults
to `None`) and echoes it in the unsigned `reproduce.json` manifest. Adding a
signed field breaks old signatures made before the field existed -- this is
the third disclosed signature break (after slice 6's source_url/source_commit)
and is pinned, not silently absorbed, by
`test_pre_slice_8_signature_over_a_record_without_tree_hash_no_longer_verifies`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from contig.bundle import _maybe_write_signature, compute_tree_sha256, write_reproduce_bundle
from contig.models import ClaimResult, ReproduceRecord, sha256_file
from contig.signing import generate_keypair, signing_available, verify_signature

HEX64 = re.compile(r"^[0-9a-f]{64}$")

requires_signing = pytest.mark.skipif(
    not signing_available(), reason="cryptography not installed"
)


def _write(root: Path, rel: str, content: bytes = b"hello") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def test_compute_tree_sha256_is_deterministic(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", b"alpha")
    _write(tmp_path, "sub/b.txt", b"beta")

    first = compute_tree_sha256(tmp_path)
    second = compute_tree_sha256(tmp_path)

    assert first is not None
    assert HEX64.match(first)
    assert first == second


def test_compute_tree_sha256_order_independent(tmp_path: Path) -> None:
    tree_a = tmp_path / "a"
    tree_b = tmp_path / "b"
    tree_a.mkdir()
    tree_b.mkdir()

    # Same files, written in a different order in each tree.
    _write(tree_a, "one.txt", b"1")
    _write(tree_a, "two.txt", b"2")
    _write(tree_a, "sub/three.txt", b"3")

    _write(tree_b, "sub/three.txt", b"3")
    _write(tree_b, "two.txt", b"2")
    _write(tree_b, "one.txt", b"1")

    assert compute_tree_sha256(tree_a) == compute_tree_sha256(tree_b)


def test_compute_tree_sha256_changes_when_a_file_changes(tmp_path: Path) -> None:
    target = _write(tmp_path, "data.txt", b"original")
    before = compute_tree_sha256(tmp_path)

    target.write_bytes(b"orIginal")  # one byte flipped

    after = compute_tree_sha256(tmp_path)
    assert before != after


def test_compute_tree_sha256_changes_when_a_file_is_added_or_removed(tmp_path: Path) -> None:
    _write(tmp_path, "keep.txt", b"keep")
    base = compute_tree_sha256(tmp_path)

    added = _write(tmp_path, "extra.txt", b"extra")
    with_extra = compute_tree_sha256(tmp_path)
    assert with_extra != base

    added.unlink()
    back_to_base = compute_tree_sha256(tmp_path)
    assert back_to_base == base


def test_compute_tree_sha256_excludes_dot_git_anywhere(tmp_path: Path) -> None:
    _write(tmp_path, "readme.txt", b"content")
    base = compute_tree_sha256(tmp_path)

    # A `.git` dir at root and a nested `sub/.git` dir.
    _write(tmp_path, ".git/HEAD", b"ref: refs/heads/main")
    _write(tmp_path, "sub/.git/config", b"[core]")

    with_git = compute_tree_sha256(tmp_path)
    assert with_git == base

    # Mutating files under either `.git` still must not move the digest.
    (tmp_path / ".git" / "HEAD").write_bytes(b"ref: refs/heads/other")
    (tmp_path / "sub" / ".git" / "config").write_bytes(b"[core]\nbare = true")
    still_base = compute_tree_sha256(tmp_path)
    assert still_base == base

    # But a real file literally named "git" (no dot) IS included.
    _write(tmp_path, "git", b"not-a-vcs-dir")
    with_git_file = compute_tree_sha256(tmp_path)
    assert with_git_file != base


def test_compute_tree_sha256_empty_dir_does_not_affect_digest(tmp_path: Path) -> None:
    tree_a = tmp_path / "a"
    tree_b = tmp_path / "b"
    tree_a.mkdir()
    tree_b.mkdir()

    _write(tree_a, "only.txt", b"content")
    (tree_a / "empty_subdir").mkdir()

    _write(tree_b, "only.txt", b"content")

    assert compute_tree_sha256(tree_a) == compute_tree_sha256(tree_b)


def _symlinks_supported(tmp_path: Path) -> bool:
    target = tmp_path / "_symlink_probe_target"
    link = tmp_path / "_symlink_probe_link"
    target.write_bytes(b"x")
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        return False
    finally:
        target.unlink(missing_ok=True)
        link.unlink(missing_ok=True)
    return True


def test_compute_tree_sha256_skips_symlinks(tmp_path: Path) -> None:
    if not _symlinks_supported(tmp_path):
        pytest.skip("symlinks not supported on this platform")

    with_link = tmp_path / "with_link"
    without_link = tmp_path / "without_link"
    with_link.mkdir()
    without_link.mkdir()

    _write(with_link, "real.txt", b"real content")
    _write(without_link, "real.txt", b"real content")

    # A symlinked *directory* elsewhere on disk, containing a file that must
    # never be hashed if the symlink is skipped/pruned rather than followed.
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    _write(outside_dir, "secret.txt", b"should never be read")

    # A symlinked file inside the tree, pointing outside the tree.
    (with_link / "link_to_file.txt").symlink_to(outside_dir / "secret.txt")
    # A symlinked directory inside the tree, pointing outside the tree.
    (with_link / "link_to_dir").symlink_to(outside_dir)

    with_link_digest = compute_tree_sha256(with_link)
    without_link_digest = compute_tree_sha256(without_link)

    # The symlinked file is skipped and the symlinked dir is pruned (never
    # followed/descended into), so both trees hash identically -- this also
    # proves containment: nothing under outside_dir ever gets read/hashed.
    assert with_link_digest == without_link_digest
    assert with_link_digest is not None


@pytest.mark.skipif(os.name == "nt", reason="chmod semantics differ on Windows")
def test_compute_tree_sha256_unreadable_file_returns_none(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("running as root: file permissions are bypassed")

    target = _write(tmp_path, "locked.txt", b"secret")
    _write(tmp_path, "other.txt", b"fine")
    original_mode = target.stat().st_mode
    target.chmod(0o000)
    try:
        result = compute_tree_sha256(tmp_path)
        assert result is None
    finally:
        target.chmod(original_mode)


def test_compute_tree_sha256_missing_or_nondir_root_returns_none(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    assert compute_tree_sha256(missing) is None

    a_file = tmp_path / "just_a_file.txt"
    a_file.write_bytes(b"content")
    assert compute_tree_sha256(a_file) is None


def test_compute_tree_sha256_matches_documented_algorithm(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", b"alpha")
    _write(tmp_path, "sub/b.txt", b"beta")
    _write(tmp_path, "sub/deeper/c.txt", b"gamma")

    # Independently recompute the digest by the published fold, without
    # calling into compute_tree_sha256's internals, to pin the algorithm.
    lines = []
    for dirpath, dirnames, filenames in os.walk(tmp_path, followlinks=False):
        dirnames[:] = [
            d
            for d in dirnames
            if d != ".git" and not (Path(dirpath) / d).is_symlink()
        ]
        for name in filenames:
            p = Path(dirpath) / name
            if p.is_symlink() or not p.is_file():
                continue
            rel = p.relative_to(tmp_path).as_posix()
            lines.append(f"{rel}\0{sha256_file(p)}\n")
    blob = "".join(sorted(lines)).encode("utf-8")
    expected = hashlib.sha256(blob).hexdigest()

    assert compute_tree_sha256(tmp_path) == expected


# --- Phase 2: signed record field + manifest echo + back-compat + the disclosed
# break -----------------------------------------------------------------------


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


def _record(**overrides) -> ReproduceRecord:
    fields = dict(
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
    fields.update(overrides)
    return ReproduceRecord(**fields)


def test_reproduce_record_source_tree_sha256_defaults_to_none_and_loads_old_json() -> None:
    # A record built without the new field defaults to None.
    record = _record()
    assert record.source_tree_sha256 is None

    # A pre-slice-8 JSON payload -- the key doesn't exist at all -- still
    # validates, and the field loads as None (back-compat).
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
        "source_url": None,
        "source_commit": None,
    }
    loaded = ReproduceRecord.model_validate_json(json.dumps(legacy_json))
    assert loaded.source_tree_sha256 is None


def test_reproduce_manifest_emits_source_tree_sha256(tmp_path: Path) -> None:
    digest = "b" * 64

    with_hash = _record(source_tree_sha256=digest)
    write_reproduce_bundle(with_hash, tmp_path / "with_hash")
    manifest = json.loads((tmp_path / "with_hash" / "reproduce.json").read_text())
    assert manifest["source_tree_sha256"] == digest

    without_hash = _record()
    write_reproduce_bundle(without_hash, tmp_path / "without_hash")
    manifest_none = json.loads((tmp_path / "without_hash" / "reproduce.json").read_text())
    assert "source_tree_sha256" in manifest_none
    assert manifest_none["source_tree_sha256"] is None


# --- disclosed caveat: a pre-slice-8 SIGNED bundle no longer verifies ----------
#
# Adding source_tree_sha256 to the record is back-compatible for LOADING (the
# test above) but NOT for a signature made before the field existed --
# `canonical_record_bytes` is `record.model_dump(mode="json")`, which now
# includes an extra null key that the old signed bytes never had. This is the
# third disclosed signature break (after slice 6's source_url/source_commit);
# it is pinned here as a KNOWN property, not a latent surprise.


def _pre_slice_8_canonical_bytes(record: ReproduceRecord) -> bytes:
    """The canonical bytes this record would have produced before slice 8.

    Rebuilt by dropping exactly the field slice 8 added -- the rest of the
    canonicalization (sorted keys, compact separators, UTF-8) is copied from
    `signing.canonical_record_bytes` so the only difference under test is the
    added key.
    """
    payload = record.model_dump(mode="json")
    old = {k: v for k, v in payload.items() if k != "source_tree_sha256"}
    assert set(payload) - set(old) == {"source_tree_sha256"}
    return json.dumps(old, sort_keys=True, separators=(",", ":")).encode("utf-8")


@requires_signing
def test_pre_slice_8_signature_over_a_record_without_tree_hash_no_longer_verifies(
    tmp_path, monkeypatch
):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key, public_key = generate_keypair()
    record = _record()  # a local run: the new field is None
    assert record.source_tree_sha256 is None

    # Sign the bytes an older Contig would have produced for this same record.
    old_signature = (
        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key))
        .sign(_pre_slice_8_canonical_bytes(record))
        .hex()
    )

    # The extra null key changes the canonical payload, so the old signature
    # does not verify -- even though nothing about the run itself changed.
    assert verify_signature(record, old_signature, public_key) is False

    # And the fresh signature over today's bytes does verify: the break is the
    # payload shape, not the signing machinery.
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)
    _maybe_write_signature(record, tmp_path)
    sidecar = json.loads((tmp_path / "signature.json").read_text())
    assert verify_signature(record, sidecar["signature"], sidecar["public_key"]) is True
    assert sidecar["signature"] != old_signature
