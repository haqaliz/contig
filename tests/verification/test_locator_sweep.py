"""Tests for the safe artifact walk substrate (candidate-sweep aspect, R1/R2)
and JSON numeric-leaf candidate enumeration (R4, D1, D4, D5).

Task 1 scope: `iter_artifacts` and the `Candidate`/`SweepSkip` data shapes.
Task 2 scope: `_json_candidates`. No size bound (Task 4), no table
enumeration (Task 3), no matching/rounding logic (aspect 2).
"""

import json
import os
from pathlib import Path

import pytest

from contig.verification.locator_inference import (
    Candidate,
    SweepSkip,
    _json_candidates,
    iter_artifacts,
)
from contig.verification.reproduce import resolve_pointer


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


def test_iter_artifacts_isolates_a_stat_failure_to_one_file(tmp_path, monkeypatch):
    _write(tmp_path, "a.json")
    _write(tmp_path, "b.json")
    _write(tmp_path, "c.json")

    real_is_symlink = Path.is_symlink

    def _flaky_is_symlink(self):
        if self.name == "a.json":
            raise OSError("stat failure forced for a.json")
        return real_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", _flaky_is_symlink)

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [tmp_path / "b.json", tmp_path / "c.json"]
    assert len(skips) == 1
    assert skips[0].source == "a.json"


def test_iter_artifacts_isolates_a_stat_failure_to_one_subdirectory(tmp_path, monkeypatch):
    dir_a = tmp_path / "dir_a"
    dir_a.mkdir()
    _write(dir_a, "inside_a.json")
    dir_b = tmp_path / "dir_b"
    dir_b.mkdir()
    _write(dir_b, "inside_b.json")

    real_is_symlink = Path.is_symlink

    def _flaky_is_symlink(self):
        if self.name == "dir_a":
            raise OSError("stat failure forced for dir_a")
        return real_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", _flaky_is_symlink)

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [dir_b / "inside_b.json"]
    assert len(skips) == 1
    assert skips[0].source == "dir_a"


# --- Task 2: _json_candidates (R4, D1, D4, D5) ---------------------------


def test_json_candidates_flat_number():
    candidates, skips = _json_candidates("m.json", '{"auc": 0.91}')

    assert candidates == [Candidate(source="m.json", kind="json", value=0.91, path="auc")]
    assert skips == []


def test_json_candidates_nested_dict():
    candidates, skips = _json_candidates("m.json", '{"m": {"auc": 0.91}}')

    assert candidates == [Candidate(source="m.json", kind="json", value=0.91, path="m.auc")]
    assert skips == []


def test_json_candidates_list():
    candidates, skips = _json_candidates("m.json", '{"xs": [1.5, 2.5]}')

    assert candidates == [
        Candidate(source="m.json", kind="json", value=1.5, path="xs[0]"),
        Candidate(source="m.json", kind="json", value=2.5, path="xs[1]"),
    ]
    assert skips == []


def test_json_candidates_list_of_dicts():
    candidates, skips = _json_candidates("m.json", '{"rows": [{"v": 3.0}]}')

    assert candidates == [Candidate(source="m.json", kind="json", value=3.0, path="rows[0].v")]
    assert skips == []


# A3 round-trip pin -- table-driven over flat/nested/list/list-of-dicts, the
# exact shapes above plus a couple more, in one document.
_ROUND_TRIP_DOC = {
    "auc": 0.91,
    "count": 7,
    "m": {"auc": 0.91, "nested": {"deep": 42}},
    "xs": [1.5, 2.5, -3.0],
    "rows": [{"v": 3.0}, {"v": 4.0, "w": {"z": 5.0}}],
    "matrix": [[1, 2], [3, 4]],
}


def test_json_candidates_round_trip_pin():
    text = json.dumps(_ROUND_TRIP_DOC)
    doc = json.loads(text)

    candidates, skips = _json_candidates("m.json", text)

    assert skips == []
    assert len(candidates) > 0
    for cand in candidates:
        assert resolve_pointer(doc, cand.path) == cand.value


def test_json_candidates_excludes_bool_null_string_and_nonfinite():
    text = (
        '{"t": true, "f": false, "n": null, "s": "0.91", '
        '"nan": NaN, "inf": Infinity, "ninf": -Infinity}'
    )

    candidates, skips = _json_candidates("m.json", text)

    assert candidates == []
    assert skips == []


def test_json_candidates_skips_key_containing_dot():
    # One skip PER KEY, not per leaf -- the reason names the key and the
    # count of numeric leaves rendered unreachable beneath it (here: 1).
    candidates, skips = _json_candidates("m.json", '{"a.b": 5.0}')

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "m.json"
    assert "a.b" in skips[0].reason
    assert "contains '.'" in skips[0].reason
    assert "1" in skips[0].reason


def test_json_candidates_skips_key_containing_bracket():
    candidates, skips = _json_candidates("m.json", '{"x[0]": 5.0}')

    assert candidates == []
    assert len(skips) == 1
    assert "x[0]" in skips[0].reason
    assert "contains '['" in skips[0].reason
    assert "1" in skips[0].reason


def test_json_candidates_skips_numeric_leaf_nested_under_unexpressible_key():
    # Still ONE skip for the whole rejected subtree, naming the outer key
    # and the count of numeric leaves lost beneath it -- not one skip per
    # individual leaf found while descending.
    candidates, skips = _json_candidates("m.json", '{"a.b": {"x": 5.0}}')

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "m.json"
    assert "a.b" in skips[0].reason
    assert "1" in skips[0].reason


def test_json_candidates_skips_one_key_names_count_of_multiple_lost_leaves():
    candidates, skips = _json_candidates(
        "m.json", '{"a.b": {"x": 1.0, "y": 2.0, "z": [3.0, 4.0]}}'
    )

    assert candidates == []
    assert len(skips) == 1
    assert "a.b" in skips[0].reason
    assert "4" in skips[0].reason


def test_json_candidates_rejected_key_with_zero_numeric_leaves_emits_no_skip():
    # A SweepSkip discloses a lost CANDIDATE. A structurally odd key that
    # costs nothing (nothing numeric underneath it) is not a loss, so it
    # must not be reported at all.
    candidates, skips = _json_candidates(
        "m.json", '{"a.b": {"s": "text", "n": null, "t": true}}'
    )

    assert candidates == []
    assert skips == []


def test_json_candidates_nested_bad_keys_do_not_double_report():
    # The OUTERMOST rejection owns the whole subtree's count. The inner
    # "c.d" key is also unexpressible, but its leaves must be counted once,
    # under the outer "a.b" skip, not reported a second time.
    candidates, skips = _json_candidates(
        "m.json", '{"a.b": {"c.d": {"x": 1.0, "y": 2.0}}}'
    )

    assert candidates == []
    assert len(skips) == 1
    assert "a.b" in skips[0].reason
    assert "c.d" not in skips[0].reason
    assert "2" in skips[0].reason


def test_json_candidates_skips_first_key_starting_with_dollar():
    # Only the FIRST token is subject to _parse_path's one-time leading '$'
    # strip -- a first-position key starting with '$' would silently
    # resolve as a different key. A later '$'-prefixed key is fine (see the
    # next test), since a literal '.' always precedes it there.
    candidates, skips = _json_candidates("m.json", '{"$foo": 5.0}')

    assert candidates == []
    assert len(skips) == 1
    assert "$foo" in skips[0].reason
    assert "starts with '$'" in skips[0].reason
    assert "1" in skips[0].reason


def test_json_candidates_allows_dollar_prefixed_key_when_not_first():
    candidates, skips = _json_candidates("m.json", '{"m": {"$foo": 5.0}}')

    assert candidates == [Candidate(source="m.json", kind="json", value=5.0, path="m.$foo")]
    assert skips == []


def test_json_candidates_skips_root_scalar_with_no_expressible_path():
    candidates, skips = _json_candidates("m.json", "5.0")

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "m.json"
    assert skips[0].reason


def test_json_candidates_malformed_json_is_a_skip_not_a_raise():
    candidates, skips = _json_candidates("m.json", "{not valid json")

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "m.json"
    assert skips[0].reason
