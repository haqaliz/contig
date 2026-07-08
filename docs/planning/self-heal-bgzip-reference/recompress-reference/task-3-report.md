# Task 3 report — Phase 3: `_recompress_reference` helper + magic-byte guard

**Branch:** `feat/self-heal-bgzip-reference/aliz`
**Scope:** `src/contig/self_heal.py`, `tests/test_self_heal.py` only (per plan Phase 3).
Not wired into `_apply_patch_and_maybe_build` (Task 4) or any other loop dispatch.

## Files changed

- `src/contig/self_heal.py`
  - `import gzip` added to the stdlib import block.
  - `_gzip_kind(path) -> str` — pure classifier. Reads up to the first 12 bytes;
    `"not_gzip"` if the file is unreadable, too short, or lacks the `1f 8b` magic.
    If the magic is present but `FLG.FEXTRA` (bit `0x04` of byte 3) is unset →
    `"plain_gzip"`. If FEXTRA is set, reads `XLEN` bytes of extra field and walks
    its subfields looking for `SI1=0x42 ('B'), SI2=0x43 ('C')` (the BGZF marker);
    found → `"bgzf"`, otherwise falls back to `"plain_gzip"`. Never raises (catches
    `OSError` around the file read).
  - `_recompress_reference(target, params, *, run_dir, built_paths)` — signature and
    return-tuple shape (`target, params, outcome, detail, continue_`) mirror
    `_build_star_index` exactly. Branches, in order:
    1. no `params["fasta"]` → `reference_recompress_unresolvable`, no redirect.
    2. `fasta` already in `built_paths` → `reference_recompress_unresolvable`
       ("Already recompressed …; failure persists."), no redirect.
    3. `_gzip_kind(fasta) != "plain_gzip"` → `reference_recompress_unresolvable`
       naming why (already BGZF, or not gzip at all) — **R2 guard: a valid BGZF
       reference is left completely untouched**, no scratch dir is even created.
    4. Otherwise: wipe+mkdir `run_dir/healed_reference` (mirrors STAR's
       rmtree-then-mkdir); target file = scratch/`<basename minus trailing ".gz">`;
       add both original `fasta` and `str(target_file)` to `built_paths` **before**
       decompressing (mirrors STAR's pre-add, closes the same one-per-run loophole);
       stream-decompress with `gzip.open(fasta, "rb")` → `open(target_file, "wb")`
       via `shutil.copyfileobj(..., length=1<<20)`, wrapped in
       `try/except (OSError, EOFError, gzip.BadGzipFile)` →
       `reference_recompress_failed` on any decompress error, no redirect (fasta
       left as-is in params).
    5. Success → `params["fasta"] = str(target_file)`, outcome
       `recompressed_reference_and_retried`, detail names original → scratch,
       `continue_=True`.
  - No changes to `detect.py`, `repair.py`, or `models.py` (out of scope per brief).
  - `_recompress_reference` and `_gzip_kind` are **not called** from
    `_apply_patch_and_maybe_build` or anywhere else yet — dispatch wiring is Task 4.

- `tests/test_self_heal.py` — appended a new section at the end of the file
  (`# _gzip_kind / _recompress_reference (recompress-reference, Phase 3)`) with 8
  new tests, following the file's existing inline-import style
  (`from contig.self_heal import _foo` inside each test body):
  - `test_gzip_kind_plain_gzip` — `gzip.compress(b">chr1\nACGT\n")` → `"plain_gzip"`.
  - `test_gzip_kind_not_gzip` — raw (non-gzip) bytes → `"not_gzip"`.
  - `test_gzip_kind_bgzf` — the canonical 28-byte BGZF EOF block
    (`1f8b08040000000000ff0600424302001b0003000000000000000000`) → `"bgzf"`.
  - `test_recompress_reference_success` — plain-gzip fixture → outcome
    `recompressed_reference_and_retried`, `continue_ is True`, scratch
    `<tmp>/healed_reference/ref.fa` exists and is byte-equal to the original
    uncompressed content, `params["fasta"]` redirected to the scratch path, both
    original and scratch paths present in `built_paths`.
  - `test_recompress_reference_no_fasta_gives_up` — empty `params` →
    `reference_recompress_unresolvable`, `continue_ is False`, no `healed_reference`
    dir created.
  - `test_recompress_reference_bgzf_input_left_untouched` — BGZF fixture as
    `params["fasta"]` → `reference_recompress_unresolvable`, `continue_ is False`,
    `params["fasta"]` unchanged, no `healed_reference` dir created (the R2 guard).
  - `test_recompress_reference_already_built_gives_up` — `fasta` pre-seeded into
    `built_paths` → `reference_recompress_unresolvable`, `continue_ is False`, no
    scratch dir, params unchanged.
  - `test_recompress_reference_decompress_failure` — gzip-magic bytes with a
    truncated/invalid deflate body → `reference_recompress_failed`,
    `continue_ is False`, `params["fasta"]` unchanged (no redirect on failure).

  (Test bodies construct `ExecutionTarget(backend="local",
  container_runtime="docker", work_dir="w")`, matching the constructor pattern
  used throughout the rest of the file — plain `ExecutionTarget()` has no
  `pipeline` field.)

## RED → GREEN evidence

**RED** (all 8 tests added first; production functions did not exist yet):

```
$ uv run pytest tests/test_self_heal.py -k "recompress or gzip_kind" -q
...
FAILED tests/test_self_heal.py::test_gzip_kind_plain_gzip - ImportError: cannot import name '_gzip_kind' from 'contig.self_heal'
FAILED tests/test_self_heal.py::test_gzip_kind_not_gzip - ImportError: cannot import name '_gzip_kind' from 'contig.self_heal'
FAILED tests/test_self_heal.py::test_gzip_kind_bgzf - ImportError: cannot import name '_gzip_kind' from 'contig.self_heal'
FAILED tests/test_self_heal.py::test_recompress_reference_success - ImportError: cannot import name '_recompress_reference' from 'contig.self_heal'
FAILED tests/test_self_heal.py::test_recompress_reference_no_fasta_gives_up
FAILED tests/test_self_heal.py::test_recompress_reference_bgzf_input_left_untouched
FAILED tests/test_self_heal.py::test_recompress_reference_already_built_gives_up
FAILED tests/test_self_heal.py::test_recompress_reference_decompress_failure
8 failed
```

Failed for the right reason: `ImportError` — neither `_gzip_kind` nor
`_recompress_reference` existed in `contig.self_heal` yet.

**GREEN** (both functions implemented in `self_heal.py`):

```
$ uv run pytest tests/test_self_heal.py -k "recompress or gzip_kind" -q
........                                                                 [100%]
8 passed
```

All 8 new tests pass. No refactor step was needed beyond the initial
implementation — it is a direct structural mirror of `_build_star_index`, so
there was nothing further to simplify.

## Whole-suite validation

```
$ uv run pytest
...
1221 passed, 1 skipped in 11.49s
```

Baseline going in was 1213 passed, 1 skipped (per task brief). Now 1221 passed, 1
skipped — exactly +8 (the new tests in this task), suite stays fully green.

## Commit

```
feat(heal): _recompress_reference — stdlib-gzip decompress + BGZF-safe guard [C2]
 2 files changed, <insertions> insertions(+)
```

Files staged and committed: `src/contig/self_heal.py`, `tests/test_self_heal.py`
only. Pre-existing unrelated worktree modifications (`docs/planning/_card/issue.md`,
`docs/planning/_card/understanding.md`, `uv.lock`) were left untouched and
unstaged, consistent with Task 2's report — out of scope for this task.

## Notes / concerns

- The BGZF detector walks the FEXTRA subfield list generically (any SI1/SI2 tag,
  not just BC) so it correctly ignores non-BC extra fields and only classifies as
  `"bgzf"` when the BC marker is actually present; a gzip file with some other
  FEXTRA subfield (no BC) correctly falls back to `"plain_gzip"`.
- Per the plan's explicit instruction, `built_paths` gets both the original fasta
  and the scratch target added **before** the decompress attempt — so a
  decompress failure still marks both paths as "built" for the run. This exactly
  mirrors `_build_star_index`'s pre-add-then-attempt ordering; a persisting
  failure on retry will hit the `built_paths` give-up branch rather than the
  gzip-kind branch, which is consistent with STAR's one-per-run guard semantics.
- Not wired into the loop yet (Task 4): `_recompress_reference` and `_gzip_kind`
  are currently unreferenced outside their own tests. This is expected per the
  brief's scope fence.
