# Task 2 report — Phase 2: propose recompress-reference patch

**Branch:** `feat/self-heal-bgzip-reference/aliz` · **Commit:** `515568fe7cf184e86112914899b76d0b8f8f3c09`
**Scope:** `src/contig/repair.py`, `tests/test_repair.py` only (per plan Phase 2).

## Files changed

- `src/contig/repair.py` — added a `reference_not_bgzf` branch to `propose_patches`,
  inserted immediately before the `missing_reference` branch, mirroring the sibling
  `missing_index` (`build_index`) reference-patch block. Returns exactly:
  ```python
  Patch(
      kind="reference",
      operation={"recompress_reference": True},
      rationale="Reference FASTA is gzip-compressed, not BGZF; decompress it and retry.",
      risk="needs_confirmation",
      expected_signal="reference readable by samtools faidx",
  )
  ```
- `tests/test_repair.py` — added `test_reference_not_bgzf_needs_confirmation_recompresses`,
  placed next to `test_missing_index_needs_confirmation_build` (before
  `test_missing_reference_needs_confirmation_swaps_reference_param`), following the
  existing `diag(failure_class)` helper style. Asserts:
  - `propose_patches(diag("reference_not_bgzf"))` returns exactly one `Patch`
  - `kind == "reference"`, `risk == "needs_confirmation"`,
    `operation == {"recompress_reference": True}`
  - `has_safe_patch(diag("reference_not_bgzf")) is False`

No changes to `detect.py`, `models.py`, `self_heal.py`, or corpus files (Task 1's
`reference_not_bgzf` FailureClass + detector branch already present from commit
`ab1e1b4` prior to this task).

## RED → GREEN evidence

**RED** (test added, production code not yet touched):

```
$ uv run pytest tests/test_repair.py -k reference_not_bgzf -v
...
tests/test_repair.py F                                                   [100%]
FAILED tests/test_repair.py::test_reference_not_bgzf_needs_confirmation_recompresses
    patches = propose_patches(diag("reference_not_bgzf"))
>   assert len(patches) == 1
E   assert 0 == 1
E    +  where 0 = len([])
1 failed, 15 deselected in 0.08s
```

Failed for the right reason: `propose_patches` fell through to `return []` for the
unhandled `reference_not_bgzf` class — no branch existed yet.

**GREEN** (branch added to `repair.py`):

```
$ uv run pytest tests/test_repair.py -v
...
tests/test_repair.py ................                                    [100%]
16 passed in 0.06s
```

All 16 tests in the file pass (15 pre-existing + 1 new).

## Whole-suite validation

```
$ uv run pytest
...
1213 passed, 1 skipped in 11.65s
```

Baseline going in was 1212 passed, 1 skipped (per task brief); now 1213 passed, 1
skipped — exactly +1 (the new repair test), suite stays fully green.

## Commit

```
515568fe7cf184e86112914899b76d0b8f8f3c09 feat(repair): propose recompress-reference patch for reference_not_bgzf [C2]
 2 files changed, 23 insertions(+)
```

Files staged and committed: `src/contig/repair.py`, `tests/test_repair.py` only.
Unrelated pre-existing worktree modifications (`docs/planning/_card/issue.md`,
`docs/planning/_card/understanding.md`, `uv.lock`) were left untouched and unstaged,
as out of scope for this task.

## Notes

- No refactor step was needed: the new branch is a straight structural mirror of the
  adjacent `missing_index`/`build_index` block, consistent with every other branch in
  `propose_patches`.
- Per the plan's design decision (§0), `risk="needs_confirmation"` (not `"safe"`) was
  used deliberately — matches the sibling reference-fix patches and routes the patch
  through the self-heal loop's gated/approval path, since rewriting the user's
  reference file needs a human veto.
