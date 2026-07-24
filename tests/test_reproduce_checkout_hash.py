"""Tests for the checkout-tree digest helper (C8 slice 8, Phase 1).

`compute_tree_sha256` is a pure, stdlib-only helper: no git, no network. All
fixture trees here are built directly on disk under `tmp_path`. The published
algorithm (walk with `os.walk(followlinks=False)`, prune `.git` dirs and
symlinked dirs, fold sorted `f"{relpath}\\0{hexdigest}\\n"` lines, sha256 the
UTF-8 blob) is pinned by test 10 so the CHANGELOG spec stays honest.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pytest

from contig.bundle import compute_tree_sha256
from contig.models import sha256_file

HEX64 = re.compile(r"^[0-9a-f]{64}$")


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
