# Final fixes report — code review Minor items (reproduce-checkout-hash, C8 slice 8)

Two Minor findings from the final code review, applied via TDD (finding 1) and a
docstring-only correction (finding 2).

## Finding 1 — directory-listing errors now surface as `None`

**Problem.** `compute_tree_sha256` (`src/contig/bundle.py`) walked with
`os.walk(base, followlinks=False)`. `os.walk`'s default `onerror=None` swallows any
error *listing* a subdirectory (e.g. a subdir with mode `0o000`): `os.walk` just
yields fewer entries for that branch, and the function returned a digest computed
over the *readable subset* of the tree — silently contradicting the docstring's
"never a partial or fabricated digest" contract. (The existing `except OSError:
return None` only ever caught errors raised while *reading a file*, via
`sha256_file`, because nothing inside the loop itself raised on a listing error.)

**Fix.** Added a module-level `_raise(err: OSError) -> None` callback and passed it
as `onerror=_raise` to `os.walk`. `os.walk` invokes `onerror` instead of silently
continuing whenever `scandir()`/`listdir()` fails on a directory; re-raising there
lets the existing `try/except OSError: return None` around the loop fold it to
`None`, exactly like an unreadable file already does. No other behavior changed:
same algorithm, same pruning (`.git`, symlinked dirs), same fold/sort/hash for the
normal case.

Docstring also tightened to say "while listing a directory or reading a file"
(was "while reading a file") and to explain why the `onerror` callback exists.

### TDD evidence

**RED** — added `test_compute_tree_sha256_unreadable_dir_returns_none` in
`tests/test_reproduce_checkout_hash.py` (mirrors the existing
`test_compute_tree_sha256_unreadable_file_returns_none`: builds a subdir containing
a file, `chmod(subdir, 0o000)`, asserts `None`, restores mode in `finally`,
skip-guarded on Windows and when running as root). Ran against the pre-fix code:

```
$ uv run pytest tests/test_reproduce_checkout_hash.py::test_compute_tree_sha256_unreadable_dir_returns_none -q
F                                                                        [100%]
=================================== FAILURES ===================================
_____________ test_compute_tree_sha256_unreadable_dir_returns_none _____________
...
>           assert result is None
E           AssertionError: assert '1e1439a8d580d3d78ef5ca6b9ef24590fb18f9eaba1a3ad3a2ee64bff557ca92' is None

tests/test_reproduce_checkout_hash.py:219: AssertionError
=========================== short test summary info ============================
FAILED tests/test_reproduce_checkout_hash.py::test_compute_tree_sha256_unreadable_dir_returns_none
```

This confirms the bug: the readable subset (`other.txt`) got hashed instead of the
whole call returning `None`.

**GREEN** — applied the `onerror=_raise` fix, reran the same test:

```
$ uv run pytest tests/test_reproduce_checkout_hash.py::test_compute_tree_sha256_unreadable_dir_returns_none -q
.                                                                        [100%]
```

## Finding 2 — stale docstring in `tests/test_reproduce_bundle.py`

**Problem.** `_pre_slice_6_canonical_bytes` (lines 327-338) and its docstring said
"the only difference under test is the added key[s]" (`source_url`,
`source_commit`). Since C8 slice 8 added `ReproduceRecord.source_tree_sha256`, the
"old" payload this helper builds still carries `source_tree_sha256: null` (it is
only dropped by `_pre_slice_8_canonical_bytes`, a separate helper), so the claim was
no longer accurate — the helper controls for two of the three post-v1 added keys,
not all of them.

**Fix.** Docstring-only change (no assertion, no dropped-keys set, no behavior
touched): it now names the two fields it actually drops (`source_url`,
`source_commit`), states plainly that later slices (slice 8's
`source_tree_sha256`) added fields it does NOT drop, and explains why that's fine —
the test only needs the old and fresh canonical payloads to *differ* so the old
signature fails to verify; it was never claiming byte-for-byte historical replay of
a real pre-slice-6 payload.

## Test run — both covering files

```
$ uv run pytest tests/test_reproduce_checkout_hash.py tests/test_reproduce_bundle.py -q
..................................                                       [100%]
```

17 tests in `tests/test_reproduce_checkout_hash.py` + 17 in
`tests/test_reproduce_bundle.py` = 34 passed, 0 failed.

## Full suite

```
$ uv run pytest -q
```

Exit code 0. 2138 collected (2137 passed, 1 skipped — the pre-existing
platform-guarded skip), 0 failed, 0 errors.

## Commit

`fix(reproduce): surface unreadable-dir errors as None; correct stale slice-6 test doc`
on `feat/reproduce-checkout-hash/aliz` (not pushed).

Commit SHA: see below (filled after commit).

## Scope discipline

Touched only: `src/contig/bundle.py`, `tests/test_reproduce_checkout_hash.py`,
`tests/test_reproduce_bundle.py` (docstring only), and this report. Left
`docs/planning/_card/issue.md` untouched — it carried a pre-existing uncommitted
edit outside this task's scope (same as noted in `phase-4-report.md`).
