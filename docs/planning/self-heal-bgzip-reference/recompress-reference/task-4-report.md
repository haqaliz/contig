# Task 4 report — wire recompress-reference into the self-heal loop

**Aspect:** `recompress-reference` (self-heal-bgzip-reference) · **Phase:** 4 (of the phased plan)
**Branch:** `feat/self-heal-bgzip-reference/aliz`
**Scope:** `src/contig/self_heal.py`, `tests/test_self_heal.py` only.

## Goal

Wire the already-built `_recompress_reference` helper (Task 3, commit `4d968a2`) into
`_apply_patch_and_maybe_build` so the full detect → diagnose → propose → approve →
recompress → retry loop actually recovers a plain-gzip'd reference FASTA end-to-end, and
give up honestly in every case it can't.

## Files touched

- `src/contig/self_heal.py`
  - `_apply_patch_and_maybe_build` (~L826-853): added one dispatch branch, immediately
    after the existing `apply_patch(...)` call and BEFORE the `build_index` gate:
    ```python
    target, params = apply_patch(target, patch, params, ceiling=ceiling)
    if patch.kind == "reference" and patch.operation.get("recompress_reference"):
        return _recompress_reference(target, params, run_dir=run_dir, built_paths=built_paths)
    if not (patch.kind == "reference" and patch.operation.get("build_index")):
        return target, params, default_outcome, None, True
    ```
    The `build_index` branch and everything after it is byte-for-byte untouched.
  - Docstring of `_apply_patch_and_maybe_build` updated to describe the new branch
    (delegates entirely to `_recompress_reference`); no behavior change.
- `tests/test_self_heal.py`
  - New section "recompress-reference: a plain-gzip'd reference is decompressed and
    retried" inserted after `test_self_heal_unparseable_index_path_fails_honestly`
    (before the existing GATK `.dict` phase section), containing:
    - `_BGZF_FAI_LOG` — the real faidx failure text (`[E::fai_build3_core] Cannot index
      files compressed with gzip, please use bgzip` + the `[faidx] Could not build fai
      index ...` line).
    - `_BGZF_REF_BYTES` — the canonical 28-byte BGZF EOF block (hex
      `1f8b08040000000000ff0600424302001b0003000000000000000000`).
    - `_PLAIN_REF_FASTA` — `b">chr1\nACGT\n"`.
    - `_bgzip_ref_executor(state, *, succeed_on_retry=True)` — mirrors `_fai_executor`:
      fails attempt 1 (and, if `succeed_on_retry=False`, every subsequent attempt) by
      writing `TRACE_INDEX` + `_BGZF_FAI_LOG`; succeeds on retry otherwise.
    - 5 new end-to-end tests (below).

## RED → GREEN evidence

### RED (before the dispatch branch existed)

Ran the 5 new tests against the unmodified loop (patch applied as a no-op reference
patch, the loop just retried blindly with the original fasta unchanged). All 5 failed,
each showing the loop took the generic `approved_and_retried` path instead of ever
calling `_recompress_reference`:

```
FAILED tests/test_self_heal.py::test_self_heal_recompresses_reference_and_retries
FAILED tests/test_self_heal.py::test_self_heal_recompress_persisting_failure_gives_up_once
FAILED tests/test_self_heal.py::test_self_heal_recompress_no_fasta_gives_up
  AssertionError: assert 'approved_and_retried' == 'reference_recompress_unresolvable'
FAILED tests/test_self_heal.py::test_self_heal_recompress_bgzf_reference_left_untouched
  AssertionError: assert 'approved_and_retried' == 'reference_recompress_unresolvable'
FAILED tests/test_self_heal.py::test_self_heal_recompress_decompress_failure_gives_up
  AssertionError: assert 'approved_and_retried' == 'reference_recompress_failed'
```

(The first two failed on `record.repair_history[-1].outcome` /
`outcomes.count("recompressed_reference_and_retried")` similarly — the loop looped to
`max_attempts` and gave up with `"gave_up"`, never invoking the recompress helper.)

### GREEN (after adding the 3-line dispatch branch)

```
uv run pytest tests/test_self_heal.py -k "recompress" -q
..........                                              [100%]
(10 passed: 5 unit tests from Task 3 + 5 new end-to-end tests)
```

## Test cases (end-to-end)

1. **`test_self_heal_recompresses_reference_and_retries`** (AC4, recovery) — `params["fasta"]`
   points at a real plain-gzip fixture (`gzip.compress(b">chr1\nACGT\n")`). Attempt 1 fails
   with the real faidx log; the loop diagnoses `reference_not_bgzf`, auto-approves the
   `needs_confirmation` recompress patch, decompresses to
   `<run_dir>/healed_reference/ref.fa` (byte-equal to the original), redirects
   `params["fasta"]`, and retries — attempt 2 succeeds. Asserts: run succeeded; last
   outcome `recompressed_reference_and_retried`; `patch.operation == {"recompress_reference": True}`;
   scratch file exists and is byte-identical; `record.parameters["fasta"]` equals the
   scratch path (the redirect actually reached the successful run's params); executor ran
   exactly twice.
2. **`test_self_heal_recompress_persisting_failure_gives_up_once`** (AC5, one-per-run guard) —
   same faidx log on both attempts. Attempt 1 recompresses and retries; attempt 2 fails
   identically, and since the scratch path (now `params["fasta"]`) is already in
   `built_paths`, the loop gives up honestly instead of looping. Asserts: exactly one
   `recompressed_reference_and_retried` outcome, the final outcome is
   `reference_recompress_unresolvable`, `record.verdict == "fail"`, and the executor ran
   exactly twice (bounded, no infinite loop).
3. **`test_self_heal_recompress_no_fasta_gives_up`** — no `"fasta"` key in params (e.g. an
   iGenomes `--genome KEY` run). Gives up on attempt 1 with `reference_recompress_unresolvable`;
   run not succeeded.
4. **`test_self_heal_recompress_bgzf_reference_left_untouched`** — `params["fasta"]` points
   at a real BGZF fixture (the 28-byte EOF block). Even though the log matches the
   detector, `_gzip_kind` recognizes real BGZF and the helper gives up
   (`reference_recompress_unresolvable`) without ever creating
   `<run_dir>/healed_reference` — asserted directly.
5. **`test_self_heal_recompress_decompress_failure_gives_up`** — a gzip-magic-but-corrupt
   fixture (`b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff" + b"\x00" * 4`, 14 bytes; passes
   the 12-byte header/FEXTRA check as `plain_gzip` but its body is not a valid deflate
   stream) raises inside the decompress `try`, giving `reference_recompress_failed`,
   `record.verdict == "fail"`, run not succeeded. (Reused the exact fixture bytes already
   proven in the Task 3 unit test `test_recompress_reference_decompress_failure`, rather
   than the shorter `b"\x1f\x8b\x08\x00" + b"garbage"` sketch in the task brief — that
   11-byte string is shorter than `_gzip_kind`'s 12-byte header read and would classify as
   `"not_gzip"` instead of triggering a real decompress failure, which would have tested
   the wrong branch.)

## Validation

```
uv run pytest tests/test_self_heal.py
150 passed in 0.28s

uv run pytest
1226 passed, 1 skipped in 11.35s
```

Baseline before this task was `1221 passed, 1 skipped`; this task added exactly 5 new
tests (1221 + 5 = 1226). Whole-suite green, no regressions.

## Commit

`feat(heal): wire recompress-reference into the self-heal loop [C2]`

## Concerns / notes

- One deliberate deviation from the task brief's example fixture for the decompress-failure
  case, explained above (functional equivalence preserved: still a "gzip magic + garbage
  body" honest-FAIL case; the byte length was adjusted so it actually reaches the
  decompress `try`/`except` branch rather than short-circuiting at `_gzip_kind`'s length
  guard).
- No production code outside the 3-line dispatch branch (+ a docstring update) was
  touched; `_recompress_reference`/`_gzip_kind` internals, `detect.py`, `repair.py`,
  `models.py`, and launch/reproduce code are all untouched, per the scope fence.
- Phase 5 (reproduce-safety: confirming `launch.json`/reproduce sidecar keeps the
  ORIGINAL fasta, not the scratch path) is explicitly out of scope for this task and is
  left for the next task.
