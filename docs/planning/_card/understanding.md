# Understanding — self-heal-custom-work-dir

Phase 2 dig note. Every citation below was verified by reading the file in this
worktree (not from memory, not from the roadmap's own line numbers, which are stale).

## What the work is really asking

`read_task_errors` is the function that feeds the failure detector the **real** error
text. Its own docstring says so:

> The main run.log only says which process failed; the real error (a tool's stderr, a
> container/platform warning) lives in the failing task's `.command.err`. The detector
> needs it (ARCHITECTURE §5.2).
> — `src/contig/runner.py:1192-1197`

It finds that text by globbing `<run_dir>/work/**/.command.err`
(`src/contig/runner.py:1198`). But the work dir Nextflow is actually given is
`target.work_dir` (`src/contig/nfconfig.py:100`, `workDir = '{target.work_dir}'`),
which the user sets with `--work-dir` (`src/contig/cli.py:400`) and which defaults to
`f"{runs_dir}/{run_id}/work"` (`src/contig/cli.py:596`).

**In the default case the two agree**, which is why this has never been caught. Set
`--work-dir` to anything else and the glob points at a directory that does not exist,
`work.is_dir()` is false, and the function returns `""` (`runner.py:1199-1200`).

## The concrete cost (verified, not asserted)

The sole call site is `src/contig/self_heal.py:1310`:

```python
log_text = read_run_log(run_dir) + "\n" + read_task_errors(run_dir)
diagnosis = diagnose_failure(events, log_text)
```

`diagnose_failure` (`src/contig/detect.py`) is a chain of regex/substring rules over
`log_text`. With the `.command.err` text gone, every specific branch misses and control
reaches the fallback at `detect.py:454-466`:

```python
if any(e.is_failure for e in events):
    crash_lines = [line for line in log_text.splitlines() if line.strip()][-1:]
    return Diagnosis(failure_class="tool_crash",
                     root_cause="A task failed with an unrecognized error.",
                     evidence=crash_lines, confidence=0.4)
```

So the damage is **three-fold**, and none of it is loud:

1. **Diagnosis degrades** to `tool_crash` @ 0.4 regardless of the true class.
2. **Self-heal stops.** `propose_patches` has no `tool_crash` branch, so it returns
   `[]` — an OOM, a missing index, a bad param, a platform mismatch all become
   "unrecognized", and the run that *was* recoverable is not recovered.
3. **The corpus is poisoned, not merely thinned.** `self_heal.py:1311-1325` appends the
   failure to the pending corpus with `log_text` as the case body and the detector's
   class as a PROVISIONAL label — so a custom-work-dir run files a case whose evidence
   is missing *and* whose label says `tool_crash`. That is moat #2 accumulating wrong
   data, which is worse than accumulating none.

## The sharp case: AWS Batch is blind by construction

`preflight_aws_batch` **requires** an `s3://` work dir and refuses the launch otherwise
(`src/contig/nfconfig.py:119-122`). So on AWS Batch the work dir is *always* remote and
`.command.err` can *never* be read off local disk. This is not a bug we can fix by
threading a path — it is a structural limit, and the slice must say so rather than
imply Batch self-heal is restored. It is a live instance of `docs/ROADMAP.md:219` R8
("running on customer compute is too brittle/varied — HPC vs cloud vs local").

## The design tension the brief did not see

The brief asks for two things that collide in the default case:

- "make an unreadable work dir an explicit honest note rather than a silent empty string"
- "keep the `run_dir`-only default so `tests/test_runner.py:60-90` passes untouched"

`tests/test_runner.py:73-76` asserts **exact equality**:

```python
def test_read_task_errors_empty_when_no_work_dirs(tmp_path):
    assert read_task_errors(tmp_path) == ""
```

And that empty return is **legitimate and common**: a run that fails before any task
starts (bad param, container pull failure, a config error) never creates `work/` at
all. An unconditional note would inject noise into `log_text` on every early failure —
and since `detect.py:457-459` takes the **last non-empty line** as `tool_crash`
evidence, a trailing note would become the recorded evidence for those runs. That is a
regression dressed as honesty.

**Resolution to carry into the PRD:** the honest note is owed for the case that is
*structurally unreadable*, not the case that is *legitimately empty*:

- work dir is **local and absent** → `""`, unchanged (no tasks ran; existing test holds)
- work dir is **remote** (`s3://`, `gs://`, `az://`, …) → an explicit one-line note,
  because no amount of looking locally will ever find it

That preserves all four existing tests byte-for-byte and puts the note exactly where a
human debugging a Batch run needs it.

## Affected areas

- `src/contig/runner.py:1191-1214` — `read_task_errors`; add an optional work-dir
  parameter, keep `run_dir` positional and the `<run_dir>/work` fallback so the three
  existing call shapes in tests are untouched.
- `src/contig/self_heal.py:1310` — the one call site. `current_target` is in scope
  (`self_heal.py:1198`, `current_target = target`), so `current_target.work_dir` is
  available. **Verified stable across attempts:** the only rebinding path is
  `apply_patch` (`self_heal.py:531-626`), which `model_copy`s `resource_limits` or
  `backend_options` only — never `work_dir`.
- `src/contig/models.py:38` — `ExecutionTarget.work_dir: str` (required, plain str).

Nothing else in `src/` hardcodes a `work` path — grepped, two hits total, both above.

## Guardrails check (CLAUDE.md)

Layer 2 (detect/self-heal) ✓. Read-path only — no manifest, verdict, exit-code, or
signature change; `LaunchManifest` deliberately stores no `work_dir`
(`models.py:408-415`) and we are not adding it ✓. No raw-read egress ✓. No correctness
over-claim — the remote case gets an honest note, not a fake fix ✓. Test-first,
synthetic fixtures, no real Nextflow in CI ✓. Not Layer 1 ✓. Not blocker-deferred work
(filed as out-of-scope for the inert-repair slice, never as infeasible) ✓.

## Open questions for the interview

1. **Note wording and placement** — does the note go into `log_text` (visible to the
   detector, and therefore to `tool_crash` evidence) or only to a surface a human
   reads? Putting it in `log_text` risks becoming the `detect.py:457` evidence line.
2. **Which schemes count as remote** — just `s3://`, or any `<scheme>://`? A generic
   "has a URI scheme and is not `file://`" rule is broader and needs no future edit.
3. **Should the remote case be caught earlier** — e.g. a one-time note at launch
   ("task-level error capture is unavailable with a remote work dir") rather than per
   failure? Cheaper for the user, but outside a read-path slice.
4. **Does `read_run_log` have the same bug?** It reads `<run_dir>/run.log`, which
   Contig itself writes (not Nextflow), so no — but confirm nothing else in the
   diagnosis context is work-dir-relative.
5. **Corpus back-fill** — existing pending-corpus cases captured from custom-work-dir
   runs carry a wrong `tool_crash` label. Out of scope, or worth a note?

## Why this survived: `read_task_errors` has no end-to-end coverage

Two facts found while checking the test surface, both verified:

1. **The self-heal suite already runs in the buggy configuration.** The canonical
   fixture is `tests/test_self_heal.py:29-30`:
   ```python
   def _target(d):
       return ExecutionTarget(backend="local", container_runtime="docker", work_dir=str(d))
   ```
   called as `_target(tmp_path / "w")` (`tests/test_self_heal.py:38`), while `run_dir`
   is `<runs_dir>/<run_id>`. So `target.work_dir` and `<run_dir>/work` have **never**
   agreed in these tests.
2. **No test anywhere writes a `.command.err` into a self-healed run.** Grepping
   `tests/` for `command.err` returns hits only in `tests/test_runner.py` (the four
   unit tests of the function in isolation) and two unrelated `test_cli_reproduce.py`
   names. Every self-heal test feeds the detector through `run.log` alone
   (`_write`, `tests/test_self_heal.py:24-26`).

Together those explain the survival: the function is unit-tested against a hand-built
`<tmp>/work` tree that matches its hardcoded assumption, and the integration path that
would expose the mismatch never supplies the file whose absence is the bug. **Both
directions are currently green for the wrong reason.**

This also hands us a clean RED test: in a `self_heal_run` test, write a `.command.err`
carrying an unambiguous classifiable signature (e.g. the platform-mismatch wording
already used at `tests/test_runner.py:64-67`) under the target's **actual** `work_dir`,
and assert the resulting diagnosis is that specific class rather than the
`tool_crash` @ 0.4 fallback (`src/contig/detect.py:454-466`). That test fails today and
passes after the fix, with no fixture contortion.

## Baseline

`uv run pytest tests/test_runner.py tests/test_detect.py -q` → 116 passed in this
worktree before any change.
