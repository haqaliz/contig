# Task 5 report — reproduce-safety (recompress-reference keeps the original fasta)

**Aspect:** `recompress-reference` (self-heal-bgzip-reference) · **Phase:** 5 (of the phased plan)
**Branch:** `feat/self-heal-bgzip-reference/aliz`
**Scope:** `tests/test_cli.py` only (no production change was needed — see verdict below).

## Goal

Verify the invariant from PRD M6 / risk R2: when `_recompress_reference` redirects
`params["fasta"]` to a run-scoped scratch path (`<run_dir>/healed_reference/<stem>.fa`),
that redirect must stay purely in-memory for the live retry and must NEVER leak into the
persisted `launch.json` — the only thing `contig rerun` / `contig resume` read to
reproduce a run. If it did leak, a later rerun would point at an ephemeral scratch file
that may not even exist.

## Investigation

1. **`src/contig/cli.py::_dispatch_run`** (L556-598): the `LaunchManifest` is constructed
   at L556-574 and written to `launch.json` at L577 — **before** `self_heal_run(...)` is
   even called (L580). Its `fasta=fasta` field (L566) is the raw `fasta` parameter handed
   into `_dispatch_run` — the user's original CLI argument — not anything derived from
   `params` (the dict that gets mutated by the heal loop). The manifest is written exactly
   once, never re-serialized after the run returns.
2. **`src/contig/self_heal.py::self_heal_run`** (L942-982+): `current_params = dict(params
   or {})` (L954) is a local variable. `_recompress_reference` (L810) does `params["fasta"]
   = str(target_file)` on this local dict — it only affects the in-process retry
   (`run_pipeline(..., params=current_params or None, ...)`, L973) and the returned
   `RunRecord.parameters` (via `_finalize`). Nothing in `self_heal.py` writes `params`/
   `current_params` to any file on disk. `run_record.json` (written by `write_bundle`, see
   `src/contig/bundle.py`) does persist `RunRecord.parameters["fasta"]` as the scratch
   path, but that file is a **provenance record of what actually ran**, not a reproduce
   source — `rerun`/`resume` never read it.
3. **`src/contig/cli.py::rerun`** (L611-666) and **`resume`** (L1259-1315): both read
   `Path(runs_dir)/run_id/"launch.json"` exclusively (`LaunchManifest.model_validate_json`)
   and re-enter `_dispatch_run` with `fasta=manifest.fasta` — the original path. Neither
   command reads `run_record.json` or anything else.

**Conclusion before writing a test:** the manifest-write ordering (write-then-run, never
rewritten) makes a leak structurally impossible today — matching the GTF-harmonization
reproduce contract (`gtf=gtf` at L567 is the same original-path pattern, already proven
safe by existing rerun tests). This predicted the "no production change" branch of the
plan, but was confirmed empirically per the plan's instruction not to assume.

## RED → GREEN evidence

Per the task instructions, a genuine RED (production code failing the test) was produced
deliberately to prove the test actually discriminates a leak, then reverted, since the
real production code was already expected (and confirmed) to be safe.

### Step 1 — test against the real (safe) code: PASSED immediately (characterization run)

```
uv run pytest tests/test_cli.py -k "recompress_reference_keeps_original_fasta" -v
tests/test_cli.py .                                                      [100%]
1 passed, 130 deselected in 0.49s
```

### Step 2 — sanity-check the test's discriminating power by injecting a temporary leak

Temporarily added (and then fully reverted) 4 lines in `_dispatch_run` right after the
`self_heal_run(...)` call, simulating exactly the bug class M6 guards against — rewriting
`launch.json.fasta` from the post-heal `record.parameters["fasta"]` (i.e. the mutated
scratch path):

```python
if "fasta" in record.parameters:
    manifest.fasta = record.parameters["fasta"]
    (manifest_dir / "launch.json").write_text(manifest.model_dump_json(indent=2))
```

Re-ran the same test — it failed exactly as expected, proving the assertion is load-bearing:

```
uv run pytest tests/test_cli.py -k "recompress_reference_keeps_original_fasta" -v
tests/test_cli.py F                                                      [100%]
FAILED tests/test_cli.py::test_run_recompress_reference_keeps_original_fasta_in_launch_json
E   AssertionError: assert '/private/var/.../erence_0/runs/bgzref/healed_reference/ref.fa' == '/private/var/.../erence_0/ref.fa.gz'
1 failed, 130 deselected in 0.12s
```

The 4-line simulated leak was then removed (`git diff --stat src/contig/cli.py` shows no
change — production code is untouched).

### Step 3 — re-ran against the real code: GREEN again

```
uv run pytest tests/test_cli.py -k "recompress_reference_keeps_original_fasta" -v
tests/test_cli.py .                                                      [100%]
1 passed, 130 deselected in 0.10s
```

## Verdict: NO PRODUCTION CHANGE NEEDED

The recompress-reference redirect was already reproduce-safe by construction (same
contract as STAR's `star_index` redirect and the GTF-harmonization redirect). This is a
**test-only** commit — a characterization/guard test that would catch a future regression
(e.g. someone "helpfully" re-deriving the manifest from `current_params` after the loop).

## Test added

`tests/test_cli.py::test_run_recompress_reference_keeps_original_fasta_in_launch_json`
(inserted after `test_rerun_from_harmonized_manifest_re_derives_harmonization`, mirroring
its style):

- Drives a real `contig run` invocation (via `CliRunner`) with a plain-gzip `--fasta` and
  a matching `--gtf` (`chr1`/`chr1`, so no reference-mismatch/harmonization branch fires —
  isolates the assertion to the recompress path only), and a fake executor
  (`_bgzip_fail_then_succeed_executor`) that fails attempt 1 with the real faidx
  not-BGZF log and succeeds on retry — same fixture/log pattern as the Task 4
  `_bgzip_ref_executor`.
- Asserts the run succeeds, the heal actually retried once (`state["n"] == 2`), and the
  scratch file (`runs/bgzref/healed_reference/ref.fa`) really exists (sanity: the
  in-memory redirect happened at all).
- Asserts `launch.json["fasta"] == str(fasta)` (the ORIGINAL plain-gzip path) and `!=`
  the scratch path.
- Asserts `run_record.json["repair_history"][-1]["outcome"] ==
  "recompressed_reference_and_retried"` and, by contrast,
  `run_record.json["parameters"]["fasta"] == str(scratch)` — explicitly documenting that
  the **operational** record (what actually ran) legitimately shows the redirect, while
  the **reproduce** source (`launch.json`) must not. This makes the distinction the
  invariant depends on visible in the test itself, not just in comments.
- Re-validates the persisted manifest via `LaunchManifest.model_validate_json` (not just
  raw JSON) and confirms the original fasta path still exists on disk (a genuinely
  re-derivable path for a real rerun). Does not exercise the CLI `rerun` command itself in
  this test, because `rerun` does not expose `--auto-approve` and would otherwise block on
  the 1800s default approval-poll timeout for the gated `needs_confirmation` reference
  patch — orthogonal to this invariant and already covered generically by the existing
  `test_rerun_from_harmonized_manifest_re_derives_harmonization`-style tests, which prove
  `rerun` reads only `launch.json`.

## Validation

```
uv run pytest tests/test_cli.py -k "recompress_reference_keeps_original_fasta" -v
1 passed, 130 deselected in 0.10s

uv run pytest
1227 passed, 1 skipped in 11.24s
```

Baseline before this task was `1226 passed, 1 skipped`; this task added exactly 1 new
test (1226 + 1 = 1227). Whole-suite green, no regressions.

## Commit

`test(heal): reproduce-safety — recompress keeps the original fasta [C2]`

## Concerns / notes

- No production code was changed. `src/contig/cli.py`, `src/contig/self_heal.py`,
  `src/contig/runner.py`, `src/contig/detect.py`, `src/contig/repair.py`, and
  `_recompress_reference`/`_gzip_kind` internals are all byte-for-byte untouched — the
  RED-phase leak injection into `cli.py` was fully reverted before the final commit
  (confirmed via `git diff --stat src/contig/cli.py` showing no output).
- Only `tests/test_cli.py` was touched: one new test plus its two small fixtures
  (`_BGZF_FAI_LOG`, `_bgzip_fail_then_succeed_executor`), inserted next to the existing
  GTF-harmonization reproduce tests it mirrors.
