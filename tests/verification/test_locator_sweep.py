"""Tests for the safe artifact walk substrate (candidate-sweep aspect, R1/R2).

Task 1 scope only: `iter_artifacts` and the `Candidate`/`SweepSkip` data
shapes. No size bound (Task 4), no JSON/table enumeration (Tasks 2/3).
"""

import os
from pathlib import Path

import pytest

from contig.verification.locator_inference import iter_artifacts


def _write(tmp_path: Path, name: str, content: str = "{}") -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_iter_artifacts_prunes_git_dir_at_top_level(tmp_path):
    _write(tmp_path, ".git/config.json")
    _write(tmp_path, "kept.json")

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [tmp_path / "kept.json"]
    assert skips == []


def test_iter_artifacts_prunes_git_dir_nested(tmp_path):
    _write(tmp_path, "a/.git/b.json")
    _write(tmp_path, "a/kept.json")

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [tmp_path / "a" / "kept.json"]
    assert skips == []


def test_iter_artifacts_skips_symlinked_file(tmp_path):
    target = _write(tmp_path, "real.json")
    link = tmp_path / "link.json"
    link.symlink_to(target)

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [target]
    assert skips == []


def test_iter_artifacts_does_not_descend_into_symlinked_dir(tmp_path):
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    _write(real_dir, "inside.json")
    link_dir = tmp_path / "link_dir"
    link_dir.symlink_to(real_dir)

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [real_dir / "inside.json"]
    assert skips == []


def test_iter_artifacts_yields_only_recognized_extensions(tmp_path):
    _write(tmp_path, "kept.json")
    _write(tmp_path, "kept.tsv", "a\tb\n")
    _write(tmp_path, "kept.csv", "a,b\n")
    _write(tmp_path, "kept.tsv.gz", "")
    _write(tmp_path, "kept.csv.gz", "")
    _write(tmp_path, "skipped.txt")
    _write(tmp_path, "skipped.ipynb")
    _write(tmp_path, "skipped.log")

    paths, skips = iter_artifacts(tmp_path)

    assert paths == sorted(
        [
            tmp_path / "kept.json",
            tmp_path / "kept.tsv",
            tmp_path / "kept.csv",
            tmp_path / "kept.tsv.gz",
            tmp_path / "kept.csv.gz",
        ]
    )
    assert skips == []


def test_iter_artifacts_sorted_by_posix_relative_path(tmp_path):
    _write(tmp_path, "b/one.json")
    _write(tmp_path, "a/two.json")
    _write(tmp_path, "a/one.json")

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [
        tmp_path / "a" / "one.json",
        tmp_path / "a" / "two.json",
        tmp_path / "b" / "one.json",
    ]
    assert skips == []


def test_iter_artifacts_sorts_even_when_walk_order_is_reversed(tmp_path, monkeypatch):
    # os.walk's on-disk ordering is filesystem-dependent and may already come
    # back sorted, which would make the above test pass without the sort
    # actually running. Force a deliberately reversed walk order here so the
    # sort step itself is what makes the assertion pass.
    _write(tmp_path, "a/one.json")
    _write(tmp_path, "b/two.json")

    real_walk = os.walk

    def _reversed_walk(*args, **kwargs):
        return reversed(list(real_walk(*args, **kwargs)))

    monkeypatch.setattr(
        "contig.verification.locator_inference.os.walk", _reversed_walk
    )

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [tmp_path / "a" / "one.json", tmp_path / "b" / "two.json"]
    assert skips == []


def test_iter_artifacts_returns_empty_for_missing_repo(tmp_path):
    missing = tmp_path / "does_not_exist"

    paths, skips = iter_artifacts(missing)

    assert paths == []
    assert skips == []


def test_iter_artifacts_returns_empty_for_non_directory_repo(tmp_path):
    file_path = _write(tmp_path, "not_a_dir.json")

    paths, skips = iter_artifacts(file_path)

    assert paths == []
    assert skips == []


def test_iter_artifacts_records_skip_for_unreadable_subdir_and_keeps_going(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permission bits")

    _write(tmp_path, "kept.json")
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    _write(blocked, "unreachable.json")
    blocked.chmod(0o000)
    try:
        paths, skips = iter_artifacts(tmp_path)
    finally:
        blocked.chmod(0o755)

    assert paths == [tmp_path / "kept.json"]
    assert len(skips) == 1
    assert skips[0].source == "blocked"
    assert skips[0].reason
