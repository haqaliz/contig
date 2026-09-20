"""Tests for the safe artifact walk substrate (candidate-sweep aspect, R1/R2),
JSON numeric-leaf candidate enumeration (R4, D1, D4, D5), table numeric-cell
candidate enumeration (R5, D2, D3, D5), and the repo-wide sweep composition
(R3, R6, R7).

Task 1 scope: `iter_artifacts` and the `Candidate`/`SweepSkip` data shapes.
Task 2 scope: `_json_candidates`. Task 3 scope: `_table_candidates`. Task 4
scope: `sweep_repo` and the size bound. No matching/rounding logic anywhere
here (aspect 2).
"""

import gzip
import json
import os
import re
from pathlib import Path

import pytest

from contig.verification.locator_inference import (
    Candidate,
    SweepSkip,
    _json_candidates,
    _table_candidates,
    iter_artifacts,
    sweep_repo,
)
from contig.verification.reproduce import (
    _read_table,
    _resolve_delimiter,
    resolve_cell,
    resolve_pointer,
)


def _write(tmp_path: Path, name: str, content: str = "{}") -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# --- Universal round-trip helpers (A3/A4) ---------------------------------
# A3/A4 used to be pinned only on two dedicated, well-behaved fixtures, while
# every HARD fixture (ragged, duplicate-header, misdetected-header,
# headerless, over-wide) asserted `candidates == [...]` and never re-resolved
# -- exactly where coordinate arithmetic is most likely to be wrong. These
# helpers make the pin UNIVERSAL: every test that enumerates candidates
# re-resolves all of them through the SHIPPED, unchanged resolvers. A
# candidate this repo emits but cannot re-resolve is a lie, wherever it came
# from.


def _assert_json_round_trip(candidates: list[Candidate], text: str) -> None:
    doc = json.loads(text)
    for cand in candidates:
        assert cand.kind == "json"
        resolved = resolve_pointer(doc, cand.path)
        assert resolved == cand.value, (
            f"{cand.path!r} re-resolves to {resolved!r}, not {cand.value!r}"
        )


def _assert_table_round_trip(candidates: list[Candidate], path: Path) -> None:
    if not candidates:
        return
    # Derive the delimiter the way `load_claims` will at reproduce time (D3:
    # we never emit one), through the shipped `_resolve_delimiter`.
    delimiter = _resolve_delimiter(path.name, None)
    assert delimiter is not None
    rows = _read_table(path, delimiter)
    for cand in candidates:
        assert cand.kind == "table"
        resolved, reason = resolve_cell(rows, cand.column, cand.row, cand.header)
        assert reason == "", f"{cand!r} did not resolve: {reason}"
        assert float(resolved) == cand.value, (
            f"{cand!r} re-resolves to {resolved!r}, not {cand.value!r}"
        )


def _over_wide_skip_numbers(skips: list[SweepSkip]) -> list[tuple[int, int, int]]:
    """Pull `(column index, header width, values lost)` out of each over-wide skip.

    C1 -- an over-wide data row silently wiping a whole featureCounts file --
    was the worst defect on this branch, and these skips are its only guard.
    Asserting just `len(skips)` would still pass if the column-index
    arithmetic were wrong, so the three numbers the arithmetic actually
    produces are parsed back out and pinned by value.
    """
    pattern = re.compile(
        r"^column index (\d+) is past the header row's (\d+) column\(s\): "
        r".*; (\d+) numeric value\(s\) beneath it are unreachable$"
    )
    out: list[tuple[int, int, int]] = []
    for skip in skips:
        match = pattern.match(skip.reason)
        assert match is not None, f"not an over-wide skip: {skip.reason!r}"
        out.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))
    return out


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


def test_iter_artifacts_skips_symlinked_file_and_discloses_it(tmp_path):
    # Containment discipline stands -- the sweep never follows a symlink. But
    # a symlinked `results.json` pointing at a legitimate in-repo target is
    # real numbers gone, and dropping it with no word is the same defect class
    # as silently truncating an over-wide table row. Not followed, but named.
    target = _write(tmp_path, "real.json")
    link = tmp_path / "link.json"
    link.symlink_to(target)

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [target]
    assert len(skips) == 1
    assert skips[0].source == "link.json"
    assert "symlink" in skips[0].reason
    assert "not followed" in skips[0].reason


def test_iter_artifacts_symlinked_file_with_uninteresting_extension_is_not_disclosed(
    tmp_path,
):
    # The extension filter runs FIRST, so a symlinked `.txt` was never a
    # candidate in the first place -- excluded by definition, nothing lost,
    # nothing to disclose. Only symlinks that WOULD have been swept are named.
    target = _write(tmp_path, "real.txt", "hi")
    (tmp_path / "link.txt").symlink_to(target)

    paths, skips = iter_artifacts(tmp_path)

    assert paths == []
    assert skips == []


def test_iter_artifacts_does_not_descend_into_symlinked_dir_but_discloses_it(tmp_path):
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    _write(real_dir, "inside.json")
    link_dir = tmp_path / "link_dir"
    link_dir.symlink_to(real_dir)

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [real_dir / "inside.json"]
    assert len(skips) == 1
    assert skips[0].source == "link_dir"
    assert "symlink" in skips[0].reason
    assert "not followed" in skips[0].reason


def test_iter_artifacts_symlinked_git_dir_is_excluded_by_definition_not_disclosed(tmp_path):
    # `.git` is pruned by name before the symlink check ever runs: it is
    # excluded by definition at any depth, so it never becomes a skip no
    # matter how it is spelled on disk.
    real_dir = tmp_path / "elsewhere"
    real_dir.mkdir()
    _write(real_dir, "inside.json")
    (tmp_path / ".git").symlink_to(real_dir)
    _write(tmp_path, "kept.json")

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [real_dir / "inside.json", tmp_path / "kept.json"]
    assert skips == []


def test_iter_artifacts_yields_only_recognized_extensions(tmp_path):
    _write(tmp_path, "kept.json")
    _write(tmp_path, "kept.tsv", "a\tb\n")
    _write(tmp_path, "kept.csv", "a,b\n")
    _write(tmp_path, "kept.tsv.gz", "")
    _write(tmp_path, "kept.csv.gz", "")
    _write(tmp_path, "kept.tab", "a\tb\n")
    _write(tmp_path, "kept.tab.gz", "")
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
            tmp_path / "kept.tab",
            tmp_path / "kept.tab.gz",
        ]
    )
    assert skips == []


def test_iter_artifacts_matches_extensions_case_insensitively(tmp_path):
    # RULING 9: the sweep walks OTHER PEOPLE'S repos, where filename casing
    # is not ours to control -- a case-sensitive filter would silently
    # under-report candidates for reasons that have nothing to do with
    # whether inference works.
    _write(tmp_path, "RESULTS.JSON")
    _write(tmp_path, "DATA.CSV", "a,b\n")
    _write(tmp_path, "counts.TSV", "a\tb\n")
    _write(tmp_path, "skipped.TXT")

    paths, skips = iter_artifacts(tmp_path)

    assert paths == sorted(
        [
            tmp_path / "RESULTS.JSON",
            tmp_path / "DATA.CSV",
            tmp_path / "counts.TSV",
        ]
    )
    assert skips == []


def test_iter_artifacts_preserves_on_disk_casing_in_the_returned_path(tmp_path):
    # A lower-cased source would not resolve on a case-sensitive filesystem
    # -- only the MATCH is case-insensitive, the emitted path is verbatim.
    p = _write(tmp_path, "Results.JSON")

    paths, skips = iter_artifacts(tmp_path)

    assert paths == [p]
    assert paths[0].name == "Results.JSON"
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
    # This is the skip class most likely to be READ (a permission-denied
    # subdirectory is the commonest real skip when sweeping someone else's
    # repo) and was the only one with no prose at all -- a bare
    # "[Errno 13] Permission denied: '/repo/blocked'" never says that A
    # SUBTREE OF ARTIFACTS WENT UNSEARCHED. The errno stays, as the tail.
    assert "could not be listed" in skips[0].reason
    assert "unsearched" in skips[0].reason
    assert "Permission denied" in skips[0].reason


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
    # A raced entry must not read as an unlistable directory: distinct
    # situations, distinct prose, same errno tail.
    assert "could not be listed" not in skips[0].reason
    assert "stat" in skips[0].reason
    assert "stat failure forced for a.json" in skips[0].reason


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
    # A raced DIRECTORY entry loses a whole subtree, and must say so -- while
    # still not claiming the directory was unlistable (it was never listed).
    assert "unsearched" in skips[0].reason
    assert "could not be listed" not in skips[0].reason
    assert "stat failure forced for dir_a" in skips[0].reason


def test_iter_artifacts_returns_skips_sorted_by_source(tmp_path, monkeypatch):
    # `found` was sorted but `skips` came back in WALK order, so the skip list
    # was non-deterministic across runs and filesystems -- in a tool whose
    # whole point is reproducibility. Force a reversed walk so the sort step
    # itself is what makes this pass.
    for d in ("b", "a"):
        (tmp_path / d).mkdir()
        target = _write(tmp_path / d, "real.json")
        (tmp_path / d / "link.json").symlink_to(target)

    real_walk = os.walk

    def _reversed_walk(*args, **kwargs):
        return reversed(list(real_walk(*args, **kwargs)))

    monkeypatch.setattr("contig.verification.locator_inference.os.walk", _reversed_walk)

    _, skips = iter_artifacts(tmp_path)

    assert [s.source for s in skips] == ["a/link.json", "b/link.json"]


# --- Task 2: _json_candidates (R4, D1, D4, D5) ---------------------------


def test_json_candidates_flat_number():
    candidates, skips = _json_candidates("m.json", '{"auc": 0.91}')

    assert candidates == [Candidate(source="m.json", kind="json", value=0.91, path="auc")]
    assert skips == []
    _assert_json_round_trip(candidates, '{"auc": 0.91}')


def test_json_candidates_nested_dict():
    candidates, skips = _json_candidates("m.json", '{"m": {"auc": 0.91}}')

    assert candidates == [Candidate(source="m.json", kind="json", value=0.91, path="m.auc")]
    assert skips == []
    _assert_json_round_trip(candidates, '{"m": {"auc": 0.91}}')


def test_json_candidates_list():
    candidates, skips = _json_candidates("m.json", '{"xs": [1.5, 2.5]}')

    assert candidates == [
        Candidate(source="m.json", kind="json", value=1.5, path="xs[0]"),
        Candidate(source="m.json", kind="json", value=2.5, path="xs[1]"),
    ]
    assert skips == []
    _assert_json_round_trip(candidates, '{"xs": [1.5, 2.5]}')


def test_json_candidates_list_of_dicts():
    candidates, skips = _json_candidates("m.json", '{"rows": [{"v": 3.0}]}')

    assert candidates == [Candidate(source="m.json", kind="json", value=3.0, path="rows[0].v")]
    assert skips == []
    _assert_json_round_trip(candidates, '{"rows": [{"v": 3.0}]}')


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
    assert doc == _ROUND_TRIP_DOC
    _assert_json_round_trip(candidates, text)


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
    _assert_json_round_trip(candidates, '{"m": {"$foo": 5.0}}')


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


# --- The round-trip backstop: token equality, not "is it parseable" -------
# `_key_expressible` hand-re-derives `_parse_path`'s grammar, and the grammar
# was hand-re-derived in THREE places, which is exactly how `expr.strip()`
# (`reproduce.py:79`) was missed. Every path below IS parseable -- it just
# parses to DIFFERENT tokens than the ones that built it, which is worse than
# unparseable: an unparseable path resolves to None, a mis-parsed one can
# resolve to ANOTHER KEY'S VALUE.


@pytest.mark.parametrize(
    ("text", "bad_key"),
    [
        ('{" x": 0.91}', " x"),
        ('{"x ": 0.91}', "x "),
        ('{"a": {"b ": 1.0}}', "b "),
        ('{"\\t x": 0.91}', "\t x"),
    ],
)
def test_json_candidates_whitespace_key_is_skipped_not_emitted(text, bad_key):
    candidates, skips = _json_candidates("m.json", text)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "m.json"
    assert "does not round-trip" in skips[0].reason
    assert repr(bad_key) in skips[0].reason


def test_json_candidates_never_emits_a_path_that_resolves_to_another_keys_value():
    # THE severe case. `" x"` and `"x"` are distinct JSON keys, but
    # `_parse_path` strips the expression before tokenizing, so the path `" x"`
    # resolves to `"x"` -- returning 0.42 for a candidate that claims 0.91.
    # A locator built on that would bind a claim to a number it never named.
    text = '{" x": 0.91, "x": 0.42}'

    candidates, skips = _json_candidates("m.json", text)

    assert [c.value for c in candidates] == [0.42]
    assert [c.path for c in candidates] == ["x"]
    assert len(skips) == 1
    _assert_json_round_trip(candidates, text)


def test_json_candidates_inner_leading_space_key_still_round_trips():
    # The guard is TOKEN EQUALITY, not a blanket whitespace ban: a leading
    # space on a NON-first segment survives `_parse_path`'s one-time
    # `expr.strip()` intact, so `a. b` really does resolve to `{" b": ...}`.
    # Pinning it proves the backstop costs zero recall rather than papering
    # over the class with a coarser rule.
    text = '{"a": {" b": 1.0}}'

    candidates, skips = _json_candidates("m.json", text)

    assert candidates == [Candidate(source="m.json", kind="json", value=1.0, path="a. b")]
    assert skips == []
    _assert_json_round_trip(candidates, text)


# --- A10: deep nesting is a skip, never a RecursionError ------------------
# "Never raises" is stated unqualified in three places, but only
# `json.JSONDecodeError` was caught. One pathological `.json` aborted every
# other artifact's sweep. The two depths below trip DIFFERENT recursions --
# the walk's, and the parser's own -- and both must be honest skips.


def test_json_candidates_nesting_too_deep_for_the_walk_is_a_skip_not_a_raise():
    # `json.loads` handles this depth fine; the module's own recursive `walk`
    # (and `_count_numeric_leaves`) is what blows the stack.
    depth = 1000
    text = "[" * depth + "1.5" + "]" * depth
    assert json.loads(text) is not None  # the parser itself copes at this depth

    candidates, skips = _json_candidates("deep.json", text)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "deep.json"
    assert "nest" in skips[0].reason


def test_json_candidates_nesting_too_deep_for_the_parser_is_a_skip_not_a_raise():
    depth = 20_000
    text = "[" * depth + "1.5" + "]" * depth
    with pytest.raises(RecursionError):
        json.loads(text)  # the parser itself gives up at this depth

    candidates, skips = _json_candidates("deeper.json", text)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "deeper.json"
    assert "nest" in skips[0].reason


# --- N1: a bare ValueError out of the parser is a skip, never a raise -----
# `json.JSONDecodeError` IS a `ValueError` subclass, which makes it easy to
# assume catching the former covers the latter. It does not: an integer
# literal longer than CPython's 4300-digit int-string conversion limit is
# rejected by `int()` INSIDE the scanner, so it surfaces as a bare
# `ValueError` and escapes a `JSONDecodeError`-only guard entirely. Same
# failure mode as the RecursionError finding -- one pathological file taking
# down every other artifact's sweep -- with a different exception type.


def test_json_candidates_over_long_integer_literal_is_a_named_skip_not_a_raise():
    text = '{"n": ' + "9" * 5000 + "}"
    with pytest.raises(ValueError) as caught:
        json.loads(text)
    # Precisely the trap: a ValueError that is NOT a JSONDecodeError.
    assert not isinstance(caught.value, json.JSONDecodeError)

    candidates, skips = _json_candidates("huge_int.json", text)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "huge_int.json"
    # It is not a syntax error, so the reason must not claim malformed JSON.
    assert "malformed JSON" not in skips[0].reason
    assert "literal" in skips[0].reason
    assert "4300" in skips[0].reason


def test_json_candidates_large_but_legal_integer_is_still_a_candidate():
    # The anti-over-reach pin. Widening the guard must not start swallowing
    # documents that parse perfectly well: an integer just under the limit is
    # an ordinary numeric leaf and must still be enumerated, not skipped.
    text = '{"n": ' + "9" * 4200 + "}"

    candidates, skips = _json_candidates("big_int.json", text)

    assert len(candidates) == 1
    assert candidates[0].path == "n"
    assert skips == []
    _assert_json_round_trip(candidates, text)


def test_json_candidates_does_not_swallow_an_unrelated_exception(monkeypatch):
    # The other half of "do not widen beyond what you can justify". The
    # never-raises contract is about what an ARTIFACT can contain, not a
    # blanket promise to bury every exception: a `TypeError` out of the
    # parser would be a bug in this repo, and recording it as an honest
    # "the data was bad" skip would disguise our fault as the user's. It
    # must still propagate. Without this, widening the guard to a bare
    # `except Exception` would break no test at all.
    def _boom(*args, **kwargs):
        raise TypeError("not a data problem")

    monkeypatch.setattr(json, "loads", _boom)

    with pytest.raises(TypeError):
        _json_candidates("m.json", '{"auc": 0.91}')


def test_json_candidates_deep_nesting_does_not_discard_what_was_already_enumerated():
    # Honesty cuts both ways: a bounded failure must not silently throw away
    # the candidates already found beside it. The shallow leaf survives AND
    # the abandoned subtree is disclosed.
    depth = 1000
    text = '{"shallow": 1.5, "deep": ' + "[" * depth + "2.5" + "]" * depth + "}"

    candidates, skips = _json_candidates("mixed.json", text)

    assert candidates == [
        Candidate(source="mixed.json", kind="json", value=1.5, path="shallow")
    ]
    assert len(skips) == 1
    assert "nest" in skips[0].reason
    _assert_json_round_trip(candidates, text)


# --- Task 3: _table_candidates (R5, D2, D3, D5) ---------------------------


def _write_table(tmp_path: Path, name: str, rows: list[list[str]], delimiter: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(delimiter.join(row) for row in rows) + "\n"
    if name.endswith(".gz"):
        with gzip.open(p, "wt", encoding="utf-8", newline="") as f:
            f.write(text)
    else:
        p.write_text(text, encoding="utf-8")
    return p


def test_table_candidates_header_ful_basic(tmp_path):
    p = _write_table(
        tmp_path,
        "de.tsv",
        [["gene_id", "log2FC"], ["ENSG1", "1.5"], ["ENSG2", "2.5"]],
        "\t",
    )

    candidates, skips = _table_candidates("de.tsv", p)

    assert candidates == [
        Candidate(source="de.tsv", kind="table", value=1.5, column="log2FC", row=0, header=True),
        Candidate(source="de.tsv", kind="table", value=2.5, column="log2FC", row=1, header=True),
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


def test_table_candidates_headerless_basic(tmp_path):
    p = _write_table(tmp_path, "counts.csv", [["10", "20"], ["30", "40"]], ",")

    candidates, skips = _table_candidates("counts.csv", p)

    assert candidates == [
        Candidate(source="counts.csv", kind="table", value=10.0, column=0, row=0, header=False),
        Candidate(source="counts.csv", kind="table", value=20.0, column=1, row=0, header=False),
        Candidate(source="counts.csv", kind="table", value=30.0, column=0, row=1, header=False),
        Candidate(source="counts.csv", kind="table", value=40.0, column=1, row=1, header=False),
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


# A4 round-trip pin -- table-driven over .tsv, .csv, and a .gz variant of
# each, so gzip-transparent reading is exercised by the same assertions.
@pytest.mark.parametrize(
    ("name", "delimiter"),
    [
        ("mixed.tsv", "\t"),
        ("mixed.csv", ","),
        ("mixed.tsv.gz", "\t"),
        ("mixed.csv.gz", ","),
        ("mixed.tab", "\t"),
        ("mixed.tab.gz", "\t"),
    ],
)
def test_table_candidates_round_trip_pin(tmp_path, name, delimiter):
    rows = [
        ["gene_id", "log2FC", "padj"],
        ["ENSG1", "-2.31", "0.001"],
        ["ENSG2", "0.5", "0.2"],
    ]
    p = _write_table(tmp_path, name, rows, delimiter)

    candidates, skips = _table_candidates(name, p)

    assert skips == []
    assert len(candidates) > 0
    _assert_table_round_trip(candidates, p)


def test_table_candidates_ragged_row_contributes_only_real_cells(tmp_path):
    # Row-major enumeration: row 0 is short a "c" cell (never an IndexError),
    # row 1 supplies all three -- order below is row-major, matching that.
    p = _write_table(
        tmp_path,
        "ragged.tsv",
        [["a", "b", "c"], ["1.0", "2.0"], ["3.0", "4.0", "5.0"]],
        "\t",
    )

    candidates, skips = _table_candidates("ragged.tsv", p)

    assert candidates == [
        Candidate(source="ragged.tsv", kind="table", value=1.0, column="a", row=0, header=True),
        Candidate(source="ragged.tsv", kind="table", value=2.0, column="b", row=0, header=True),
        Candidate(source="ragged.tsv", kind="table", value=3.0, column="a", row=1, header=True),
        Candidate(source="ragged.tsv", kind="table", value=4.0, column="b", row=1, header=True),
        Candidate(source="ragged.tsv", kind="table", value=5.0, column="c", row=1, header=True),
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


# --- Over-wide data rows: the OTHER ragged direction ----------------------
# Ragged handling was ONE-DIRECTIONAL. A data row SHORTER than the header is
# handled (`continue`); a data row LONGER than the header was enumerated by
# NOTHING and disclosed by NOTHING, because the scan is bounded by
# `enumerate(header_row)`. Those cells are genuinely NOT ADDRESSABLE --
# `resolve_cell` bounds an int column by the HEADER row's width, not the data
# row's -- so the fix is to SKIP, loudly, never to emit a coordinate that can
# never bind.


def test_resolve_cell_cannot_address_a_cell_past_the_header_width(tmp_path):
    # The premise of the skip-don't-emit choice, pinned against the SHIPPED
    # resolver rather than asserted in a comment. If this ever stops being
    # true, emitting these cells becomes the better fix.
    rows = [["gene", "log2FC"], ["ENSG1", "1.5", "0.001"]]

    resolved, reason = resolve_cell(rows, 2, 0, True)

    assert resolved is None
    assert "out of range" in reason


def test_table_candidates_over_wide_data_rows_are_disclosed_not_silently_dropped(tmp_path):
    # 'gene,log2FC' with three-cell data rows: 0.001 and 0.002 used to vanish
    # with ZERO skips. A claim that fails to bind because we silently dropped
    # its file is indistinguishable, to the user, from an honest miss.
    p = _write_table(
        tmp_path,
        "wide.csv",
        [["gene", "log2FC"], ["ENSG1", "1.5", "0.001"], ["ENSG2", "2.5", "0.002"]],
        ",",
    )

    candidates, skips = _table_candidates("wide.csv", p)

    assert candidates == [
        Candidate(source="wide.csv", kind="table", value=1.5, column="log2FC", row=0, header=True),
        Candidate(source="wide.csv", kind="table", value=2.5, column="log2FC", row=1, header=True),
    ]
    _assert_table_round_trip(candidates, p)
    assert [s.source for s in skips] == ["wide.csv"]
    # Column index 2, past a 2-column header, 2 values lost (0.001, 0.002).
    # A bare `"2" in reason` could not tell those three numbers apart.
    assert _over_wide_skip_numbers(skips) == [(2, 2, 2)]


def test_table_candidates_leading_comment_line_discloses_the_whole_file(tmp_path):
    # THE severe case, and an ordinary bioinformatics table shape: a
    # `# Program:featureCounts v2.0.1` first line makes D2 see ONE non-numeric
    # cell in row 0, declare a ONE-COLUMN header, and drop every number off
    # the right edge. Before the fix: 0 candidates and 0 SKIPS -- a whole file
    # silently empty.
    p = _write_table(
        tmp_path,
        "counts.tsv",
        [
            ["# Program:featureCounts v2.0.1"],
            ["Geneid", "Length", "sample1"],
            ["ENSG1", "1500", "42"],
            ["ENSG2", "900", "7"],
        ],
        "\t",
    )

    candidates, skips = _table_candidates("counts.tsv", p)

    assert candidates == []
    # One skip per over-wide column that held at least one number, ordered by
    # column index: col 1 (1500, 900) and col 2 (42, 7), both past a
    # ONE-column header. "Geneid"/"Length"/"sample1" are not numeric and cost
    # nothing, so no column-0 skip.
    assert {s.source for s in skips} == {"counts.tsv"}
    assert _over_wide_skip_numbers(skips) == [(1, 1, 2), (2, 1, 2)]


def test_table_candidates_leading_blank_line_discloses_the_whole_file(tmp_path):
    # A leading blank line gives a ZERO-column header row, so literally every
    # cell in the file is past the right edge. Before the fix: 0 candidates,
    # 0 skips.
    p = tmp_path / "blank_first.csv"
    p.write_text("\ngene,log2FC\nENSG1,1.5\n", encoding="utf-8")

    candidates, skips = _table_candidates("blank_first.csv", p)

    assert candidates == []
    assert [s.source for s in skips] == ["blank_first.csv"]
    # A ZERO-column header: only the 1.5 is numeric, at column index 1.
    assert _over_wide_skip_numbers(skips) == [(1, 0, 1)]


def test_table_candidates_over_wide_column_with_no_numeric_cells_emits_no_skip(tmp_path):
    # The module's existing "zero lost => no skip" rule, applied to this new
    # class: an over-wide column holding only text costs nothing.
    p = _write_table(
        tmp_path,
        "wide_text.csv",
        [["gene", "log2FC"], ["ENSG1", "1.5", "note"], ["ENSG2", "2.5", "other"]],
        ",",
    )

    candidates, skips = _table_candidates("wide_text.csv", p)

    assert candidates == [
        Candidate(
            source="wide_text.csv", kind="table", value=1.5, column="log2FC", row=0, header=True
        ),
        Candidate(
            source="wide_text.csv", kind="table", value=2.5, column="log2FC", row=1, header=True
        ),
    ]
    _assert_table_round_trip(candidates, p)
    assert skips == []


def test_table_candidates_headerless_over_wide_rows_are_emitted_not_skipped(tmp_path):
    # The over-wide problem is HEADER-MODE ONLY. Headerless, `resolve_cell`
    # bounds the column by the TARGET ROW's width, so an over-wide cell IS
    # addressable and must be a candidate, not a skip -- the round-trip
    # helper is what proves the distinction is real rather than assumed.
    p = _write_table(tmp_path, "wide_headerless.csv", [["1.0", "2.0"], ["3.0", "4.0", "5.0"]], ",")

    candidates, skips = _table_candidates("wide_headerless.csv", p)

    assert [c.value for c in candidates] == [1.0, 2.0, 3.0, 4.0, 5.0]
    _assert_table_round_trip(candidates, p)
    assert skips == []


def test_table_candidates_numeric_string_cell_is_a_candidate(tmp_path):
    # D5: the opposite of the JSON rule -- a table cell is always a string,
    # so a numeric-looking one ("5.0") IS a candidate. "NA" is not numeric
    # and is simply excluded, not skipped (nothing was lost).
    p = _write_table(tmp_path, "m.csv", [["label", "value"], ["NA", "5.0"]], ",")

    candidates, skips = _table_candidates("m.csv", p)

    assert candidates == [
        Candidate(source="m.csv", kind="table", value=5.0, column="value", row=0, header=True)
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


def test_table_candidates_empty_table(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("")

    candidates, skips = _table_candidates("empty.csv", p)

    assert candidates == []
    assert skips == []


def test_table_candidates_skips_duplicate_header_name(tmp_path):
    # resolve_cell calls a duplicate header name ambiguous -- emitting a
    # locator for it would propose one that can never resolve. ONE skip for
    # the whole duplicate name, naming the duplicate count and how many
    # numeric candidates are lost beneath it (here: 2, one per data-row
    # cell under either "a" column).
    p = _write_table(tmp_path, "dup.csv", [["a", "a", "b"], ["1.0", "2.0", "3.0"]], ",")

    candidates, skips = _table_candidates("dup.csv", p)

    assert candidates == [
        Candidate(source="dup.csv", kind="table", value=3.0, column="b", row=0, header=True)
    ]
    _assert_table_round_trip(candidates, p)
    assert len(skips) == 1
    assert skips[0].source == "dup.csv"
    assert "'a'" in skips[0].reason
    assert "2" in skips[0].reason
    assert "numeric value(s)" in skips[0].reason
    assert "numeric candidate(s)" not in skips[0].reason


def test_table_candidates_duplicate_header_with_no_numeric_cells_emits_no_skip(tmp_path):
    # Mirrors the JSON "rejected key with zero numeric leaves" rule: nothing
    # numeric lives under the duplicate name, so nothing was lost, so there
    # is nothing to disclose.
    p = _write_table(tmp_path, "dup2.csv", [["a", "a", "b"], ["x", "y", "3.0"]], ",")

    candidates, skips = _table_candidates("dup2.csv", p)

    assert candidates == [
        Candidate(source="dup2.csv", kind="table", value=3.0, column="b", row=0, header=True)
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


def test_table_candidates_excludes_non_finite_values(tmp_path):
    # Mirrors D4's JSON exclusion for a different reason here: the A4
    # round-trip pin checks float(resolved) == cand.value, which can never
    # hold for NaN (NaN != NaN), so a non-finite cell must never become a
    # candidate's value even though float("nan") itself doesn't raise.
    p = _write_table(tmp_path, "nonfinite.csv", [["a", "b"], ["nan", "5.0"]], ",")

    candidates, skips = _table_candidates("nonfinite.csv", p)

    assert candidates == [
        Candidate(source="nonfinite.csv", kind="table", value=5.0, column="b", row=0, header=True)
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


def test_table_candidates_missing_file_is_a_skip_not_a_raise(tmp_path):
    p = tmp_path / "does_not_exist.csv"

    candidates, skips = _table_candidates("does_not_exist.csv", p)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "does_not_exist.csv"
    assert skips[0].reason


def test_table_candidates_non_utf8_file_is_a_skip_not_a_raise(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_bytes(b"a,b\n\xff\xfe,1.0\n")

    candidates, skips = _table_candidates("bad.csv", p)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "bad.csv"
    assert skips[0].reason


def test_table_candidates_corrupt_gzip_is_a_skip_not_a_raise(tmp_path):
    p = tmp_path / "bad.tsv.gz"
    with gzip.open(p, "wt", encoding="utf-8", newline="") as f:
        f.write("a\tb\n1.0\t2.0\n")
    full_bytes = p.read_bytes()
    p.write_bytes(full_bytes[: len(full_bytes) // 2])

    candidates, skips = _table_candidates("bad.tsv.gz", p)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "bad.tsv.gz"
    assert skips[0].reason


def test_table_candidates_uppercase_gz_suffix_is_a_named_case_sensitivity_skip(tmp_path):
    # `iter_artifacts` matches ".gz"-family extensions case-insensitively
    # (fix round 1), so a file literally named "DATA.CSV.GZ" is reachable.
    # But the shipped `_read_table` detects gzip via a case-SENSITIVE
    # `endswith(".gz")`, so it would open this file as plain text and fail
    # to decode/parse it -- landing on the generic "could not be read"
    # skip, which would misdiagnose a simple casing mismatch as corruption.
    # `_table_candidates` must instead name the real cause up front.
    p = tmp_path / "DATA.CSV.GZ"
    with gzip.open(p, "wt", encoding="utf-8", newline="") as f:
        f.write("a,b\n1.0,2.0\n")

    candidates, skips = _table_candidates("DATA.CSV.GZ", p)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "DATA.CSV.GZ"
    # Assert on the distinguishing substance of the message, not the whole
    # string: it must name the file and the case-sensitivity cause, not
    # the generic "could not be read" reason used for genuine corruption.
    assert "DATA.CSV.GZ" in skips[0].reason
    assert "case-sensitive" in skips[0].reason
    assert "could not be read" not in skips[0].reason


def test_table_candidates_unrecognized_extension_is_a_skip_not_a_raise(tmp_path):
    p = _write_table(tmp_path, "weird.psv", [["a", "b"], ["1.0", "2.0"]], "|")

    candidates, skips = _table_candidates("weird.psv", p)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "weird.psv"
    assert skips[0].reason


# --- D2 header-heuristic boundary cases -----------------------------------
# The hazard specific to this task: D2 ("row 0 is a header iff no cell in
# it parses as a float") is an uncalibrated engineering default that can
# silently shift every row index in a file. These tests pin exactly what
# the literal rule does at its ambiguous edges -- not what a cleverer
# heuristic might do.


def test_table_candidates_header_heuristic_boundary_genuinely_data_row_consumed_as_header(
    tmp_path,
):
    # Every row here is really a single-column data sample (no header row
    # exists at all), but row 0 happens to contain no numeric cell, so D2
    # calls it a header anyway. "control" is consumed as the column name,
    # and what was really the second data sample becomes row=0 -- the
    # documented misdetection, pinned exactly, not fixed.
    p = _write_table(tmp_path, "no_real_header.tsv", [["control"], ["1.5"], ["2.5"]], "\t")

    candidates, skips = _table_candidates("no_real_header.tsv", p)

    assert candidates == [
        Candidate(
            source="no_real_header.tsv",
            kind="table",
            value=1.5,
            column="control",
            row=0,
            header=True,
        ),
        Candidate(
            source="no_real_header.tsv",
            kind="table",
            value=2.5,
            column="control",
            row=1,
            header=True,
        ),
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


def test_table_candidates_header_heuristic_boundary_mixed_first_row_is_headerless(tmp_path):
    # D2 is a whole-row test: ONE numeric cell anywhere in row 0 ("1") makes
    # the entire table headerless, even though "sample" alongside it reads
    # like a header label. No per-column cleverness -- pinned as headerless.
    p = _write_table(tmp_path, "mixed_first_row.csv", [["sample", "1"], ["a", "2.5"]], ",")

    candidates, skips = _table_candidates("mixed_first_row.csv", p)

    assert candidates == [
        Candidate(
            source="mixed_first_row.csv", kind="table", value=1.0, column=1, row=0, header=False
        ),
        Candidate(
            source="mixed_first_row.csv", kind="table", value=2.5, column=1, row=1, header=False
        ),
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


def test_table_candidates_header_heuristic_boundary_single_text_row_yields_no_candidates(
    tmp_path,
):
    # A single-row, all-text table: D2 calls it a header, leaving zero data
    # rows -- correctly zero candidates, not an IndexError on rows[1:].
    p = _write_table(tmp_path, "single_header_only.csv", [["a", "b"]], ",")

    candidates, skips = _table_candidates("single_header_only.csv", p)

    assert candidates == []
    assert skips == []


def test_table_candidates_header_heuristic_boundary_single_numeric_row_is_headerless(tmp_path):
    # A single-row table where that row parses as numbers: D2 calls it
    # headerless, so the one row is itself data (row=0), not consumed.
    p = _write_table(tmp_path, "single_numeric_row.csv", [["1.0", "2.0"]], ",")

    candidates, skips = _table_candidates("single_numeric_row.csv", p)

    assert candidates == [
        Candidate(
            source="single_numeric_row.csv", kind="table", value=1.0, column=0, row=0, header=False
        ),
        Candidate(
            source="single_numeric_row.csv", kind="table", value=2.0, column=1, row=0, header=False
        ),
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


def test_table_candidates_header_heuristic_boundary_single_column_header_ful(tmp_path):
    p = _write_table(tmp_path, "single_col.csv", [["value"], ["5.0"], ["6.0"]], ",")

    candidates, skips = _table_candidates("single_col.csv", p)

    assert candidates == [
        Candidate(
            source="single_col.csv", kind="table", value=5.0, column="value", row=0, header=True
        ),
        Candidate(
            source="single_col.csv", kind="table", value=6.0, column="value", row=1, header=True
        ),
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


def test_table_candidates_header_heuristic_boundary_single_column_headerless(tmp_path):
    p = _write_table(tmp_path, "single_col_headerless.csv", [["5.0"], ["6.0"]], ",")

    candidates, skips = _table_candidates("single_col_headerless.csv", p)

    assert candidates == [
        Candidate(
            source="single_col_headerless.csv",
            kind="table",
            value=5.0,
            column=0,
            row=0,
            header=False,
        ),
        Candidate(
            source="single_col_headerless.csv",
            kind="table",
            value=6.0,
            column=0,
            row=1,
            header=False,
        ),
    ]
    assert skips == []
    _assert_table_round_trip(candidates, p)


# --- Task 4: sweep_repo (R3, R6, R7, A2, A9, A10) -------------------------


def test_sweep_repo_mixed_fixture_returns_right_candidates_and_skips(tmp_path, monkeypatch):
    # A mixed repo: a plain JSON, a TSV, a gzipped CSV, a malformed JSON, and
    # (with the cap shrunk rather than writing a real 8 MiB fixture -- see
    # test_reproduce.py's own "cap is shrunk" idiom) an oversized JSON.
    monkeypatch.setattr("contig.verification.locator_inference._MAX_MATCH_BYTES", 100)

    _write(tmp_path, "metrics.json", '{"auc": 0.91}')
    _write_table(tmp_path, "de.tsv", [["gene_id", "log2FC"], ["ENSG1", "1.5"]], "\t")
    _write_table(tmp_path, "counts.csv.gz", [["a", "b"], ["1.0", "2.0"]], ",")
    _write(tmp_path, "broken.json", "{not valid json")
    oversized = _write(tmp_path, "oversized.json", '{"padding": "' + "x" * 200 + '"}')
    assert oversized.stat().st_size > 100

    candidates, skips = sweep_repo(tmp_path)

    by_source: dict[str, list[Candidate]] = {}
    for cand in candidates:
        by_source.setdefault(cand.source, []).append(cand)

    assert by_source["metrics.json"] == [
        Candidate(source="metrics.json", kind="json", value=0.91, path="auc")
    ]
    assert by_source["de.tsv"] == [
        Candidate(source="de.tsv", kind="table", value=1.5, column="log2FC", row=0, header=True)
    ]
    assert by_source["counts.csv.gz"] == [
        Candidate(source="counts.csv.gz", kind="table", value=1.0, column="a", row=0, header=True),
        Candidate(source="counts.csv.gz", kind="table", value=2.0, column="b", row=0, header=True),
    ]
    assert "oversized.json" not in by_source

    skip_sources = {s.source for s in skips}
    assert skip_sources == {"broken.json", "oversized.json"}


def test_sweep_repo_oversized_json_artifact_is_a_named_skip_with_zero_candidates(
    tmp_path, monkeypatch
):
    # A2, for the JSON branch.
    monkeypatch.setattr("contig.verification.locator_inference._MAX_MATCH_BYTES", 10)
    p = _write(tmp_path, "huge.json", '{"auc": 0.91}')
    size = p.stat().st_size
    assert size > 10

    candidates, skips = sweep_repo(tmp_path)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "huge.json"
    assert str(size) in skips[0].reason


def test_sweep_repo_oversized_table_artifact_is_a_named_skip_with_zero_candidates(
    tmp_path, monkeypatch
):
    # A2, for the table branch -- the size bound is checked BEFORE dispatch,
    # regardless of which enumerator would otherwise have handled the file.
    monkeypatch.setattr("contig.verification.locator_inference._MAX_MATCH_BYTES", 10)
    p = _write_table(tmp_path, "big.csv", [["a", "b"], ["1.0", "2.0"]], ",")
    size = p.stat().st_size
    assert size > 10

    candidates, skips = sweep_repo(tmp_path)

    assert candidates == []
    assert len(skips) == 1
    assert skips[0].source == "big.csv"
    assert str(size) in skips[0].reason


def test_sweep_repo_propagates_the_walks_own_skips(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permission bits")

    _write(tmp_path, "kept.json", '{"auc": 0.91}')
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    _write(blocked, "unreachable.json", '{"x": 1}')
    blocked.chmod(0o000)
    try:
        candidates, skips = sweep_repo(tmp_path)
    finally:
        blocked.chmod(0o755)

    assert [c.source for c in candidates] == ["kept.json"]
    assert len(skips) == 1
    assert skips[0].source == "blocked"
    assert skips[0].reason


def test_sweep_repo_dispatches_uppercase_extensions_to_the_right_enumerator(tmp_path):
    # RESULTS.JSON and DATA.CSV are reachable via iter_artifacts's
    # case-insensitive match -- a case-SENSITIVE dispatch check here would
    # let them fall through and vanish with no skip at all.
    _write(tmp_path, "RESULTS.JSON", '{"auc": 0.91}')
    _write_table(tmp_path, "DATA.CSV", [["a", "b"], ["1.0", "2.0"]], ",")

    candidates, skips = sweep_repo(tmp_path)

    by_source: dict[str, list[Candidate]] = {}
    for cand in candidates:
        by_source.setdefault(cand.source, []).append(cand)

    assert by_source["RESULTS.JSON"] == [
        Candidate(source="RESULTS.JSON", kind="json", value=0.91, path="auc")
    ]
    assert by_source["DATA.CSV"] == [
        Candidate(source="DATA.CSV", kind="table", value=1.0, column="a", row=0, header=True),
        Candidate(source="DATA.CSV", kind="table", value=2.0, column="b", row=0, header=True),
    ]
    assert skips == []


def test_sweep_repo_isolates_a_read_failure_to_one_artifact(tmp_path, monkeypatch):
    _write(tmp_path, "a.json", '{"auc": 0.91}')
    _write(tmp_path, "b.json", '{"acc": 0.5}')

    real_read_text = Path.read_text

    def _flaky_read_text(self, *args, **kwargs):
        if self.name == "a.json":
            raise OSError("read failure forced for a.json")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _flaky_read_text)

    candidates, skips = sweep_repo(tmp_path)

    assert [c.source for c in candidates] == ["b.json"]
    assert len(skips) == 1
    assert skips[0].source == "a.json"
    assert skips[0].reason


def test_sweep_repo_isolates_a_stat_failure_to_one_artifact(tmp_path, monkeypatch):
    _write(tmp_path, "a.json", '{"auc": 0.91}')
    _write(tmp_path, "b.json", '{"acc": 0.5}')

    real_stat = Path.stat

    def _flaky_stat(self, *args, follow_symlinks=True, **kwargs):
        # `Path.lstat()` (which `iter_artifacts`'s own `is_symlink()` check
        # goes through) is implemented as `self.stat(follow_symlinks=False)`
        # -- a mock that fired unconditionally on "a.json" would actually be
        # caught by iter_artifacts's OWN try/except (already pinned in
        # Task 1), never reaching sweep_repo's own stat() call at all, and
        # this test would pass for the wrong reason. Firing only on the
        # default `follow_symlinks=True` call isolates it to sweep_repo's
        # own size-check stat(), simulating a delete race between the walk
        # finding the file and sweep_repo statting it.
        if self.name == "a.json" and follow_symlinks:
            raise OSError("stat failure forced for a.json")
        return real_stat(self, *args, follow_symlinks=follow_symlinks, **kwargs)

    monkeypatch.setattr(Path, "stat", _flaky_stat)

    candidates, skips = sweep_repo(tmp_path)

    assert [c.source for c in candidates] == ["b.json"]
    assert len(skips) == 1
    assert skips[0].source == "a.json"
    assert skips[0].reason


def test_sweep_repo_candidates_are_ordered_by_source_path(tmp_path):
    _write(tmp_path, "b/two.json", '{"x": 2.0}')
    _write(tmp_path, "a/one.json", '{"x": 1.0}')

    candidates, skips = sweep_repo(tmp_path)

    assert [c.source for c in candidates] == ["a/one.json", "b/two.json"]
    assert skips == []


def test_sweep_repo_empty_repo_yields_nothing(tmp_path):
    candidates, skips = sweep_repo(tmp_path)

    assert candidates == []
    assert skips == []


def test_sweep_repo_over_long_integer_literal_does_not_take_down_the_sweep(tmp_path):
    # THE assertion that matters for N1: one pathological artifact must not
    # cost every other artifact in the repo its candidates. Before the fix
    # the bare ValueError propagated out of `sweep_repo` and the healthy
    # sibling's 0.91 was lost with the exception.
    _write(tmp_path, "huge_int.json", '{"n": ' + "9" * 5000 + "}")
    _write(tmp_path, "ok.json", '{"ok": 0.91}')

    candidates, skips = sweep_repo(tmp_path)  # must never raise

    assert candidates == [Candidate(source="ok.json", kind="json", value=0.91, path="ok")]
    assert [s.source for s in skips] == ["huge_int.json"]
    assert "malformed JSON" not in skips[0].reason


def test_sweep_repo_skips_are_ordered_by_source_path(tmp_path):
    # `sweep_repo`'s docstring promised POSIX-relative-path order for the
    # WHOLE return, but only `candidates` was ordered: the walk's own skips
    # came back in walk order and were then followed by per-artifact skips.
    # A reproducibility tool cannot ship a non-deterministic disclosure list.
    _write(tmp_path, "z/broken.json", "{not valid json")
    _write(tmp_path, "a/broken.json", "{not valid json")
    _write(tmp_path, "m/broken.json", "{not valid json")
    real = _write(tmp_path, "a/real.json", '{"x": 1.0}')
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "link.json").symlink_to(real)

    _, skips = sweep_repo(tmp_path)

    assert [s.source for s in skips] == sorted(s.source for s in skips)
    assert [s.source for s in skips] == [
        "a/broken.json",
        "b/link.json",
        "m/broken.json",
        "z/broken.json",
    ]


def test_sweep_repo_reads_json_as_utf8_not_the_platform_locale(tmp_path, monkeypatch):
    # A bare `read_text()` uses the PLATFORM LOCALE encoding while
    # `_read_table` passes an explicit `encoding="utf-8"`. Under a non-UTF-8
    # locale a perfectly valid JSON artifact degrades to a misleading "could
    # not read artifact" skip and the sweep becomes MACHINE-DEPENDENT --
    # unacceptable for a reproducibility tool. The encoding is not
    # observable from the result on a UTF-8 host, so pin the call itself.
    seen: list[object] = []
    real_read_text = Path.read_text

    def _spy_read_text(self, encoding=None, **kwargs):
        seen.append(encoding)
        return real_read_text(self, encoding=encoding, **kwargs)

    monkeypatch.setattr(Path, "read_text", _spy_read_text)
    _write(tmp_path, "metrics.json", '{"auc": 0.91, "label": "échantillon"}')

    candidates, skips = sweep_repo(tmp_path)

    assert [c.value for c in candidates] == [0.91]
    assert skips == []
    assert seen == ["utf-8"]


def test_skip_reasons_use_one_vocabulary_for_lost_numbers():
    # Two skips, adjacent lines in one sidecar, described the same concept
    # as "numeric leaf(s)" (JSON) and "numeric candidate(s)" (table). A
    # sidecar a human reads to decide whether a miss was honest should not
    # make them wonder whether two names mean two things.
    _, json_skips = _json_candidates("m.json", '{"a.b": {"x": 1.0}}')

    assert len(json_skips) == 1
    assert "numeric value(s)" in json_skips[0].reason
    assert "numeric leaf(s)" not in json_skips[0].reason
    assert "numeric candidate(s)" not in json_skips[0].reason


# --- A10 wild-input sweep: never an exception, always a skip or nothing ---


def test_sweep_repo_wild_json_inputs_never_raise(tmp_path):
    _write(tmp_path, "empty.json", "")
    (tmp_path / "binary.json").write_bytes(b"\x00\x01\x02\xff\xfe")
    _write(tmp_path, "scalar.json", "5.0")
    (tmp_path / "bom.json").write_bytes(b"\xef\xbb\xbf" + b'{"auc": 0.91}')
    _write(
        tmp_path,
        "deep.json",
        json.dumps({"a": {"b": {"c": {"d": {"e": 1.5}}}}}),
    )
    # Pathologically deep: one such file used to abort EVERY other
    # artifact's sweep with an uncaught RecursionError.
    _write(tmp_path, "abyss.json", "[" * 1000 + "1.5" + "]" * 1000)

    candidates, skips = sweep_repo(tmp_path)  # must never raise

    by_source: dict[str, list[Candidate]] = {}
    for cand in candidates:
        by_source.setdefault(cand.source, []).append(cand)
    skip_sources = {s.source for s in skips}

    # Every wild file either produced a skip or, for the ones with a real
    # numeric leaf, a candidate -- never silently neither, never a raise.
    assert "empty.json" in skip_sources
    assert "binary.json" in skip_sources
    assert "scalar.json" in skip_sources
    assert "bom.json" in skip_sources
    assert by_source["deep.json"] == [
        Candidate(source="deep.json", kind="json", value=1.5, path="a.b.c.d.e")
    ]
    assert "abyss.json" in skip_sources


def test_sweep_repo_wild_table_inputs_never_raise(tmp_path):
    (tmp_path / "binary.csv").write_bytes(b"\x00\x01\x02\xff\xfe")
    _write(tmp_path, "empty.tsv", "")

    candidates, skips = sweep_repo(tmp_path)  # must never raise

    assert candidates == []
    skip_sources = {s.source for s in skips}
    assert "binary.csv" in skip_sources
    # An empty table yields no candidates and no skip -- nothing was lost.
    assert "empty.tsv" not in skip_sources
