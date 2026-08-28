# PRD — self-heal-custom-work-dir

**Status:** draft for review
**Branch:** `feat/self-heal-custom-work-dir/aliz`
**Capability:** C2 (self-heal breadth) — closes deferral item (a)
**Sources:** `docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`

---

## Problem Statement

`read_task_errors` (`src/contig/runner.py:1191-1214`) is the function that feeds the
failure detector the **real** error text. Its own docstring states the stakes:

> The main run.log only says which process failed; the real error (a tool's stderr, a
> container/platform warning) lives in the failing task's `.command.err`. The detector
> needs it (ARCHITECTURE §5.2).

It locates that text by globbing `<run_dir>/work/**/.command.err`
(`runner.py:1198`). But the work dir Nextflow is actually given is `target.work_dir`
(`src/contig/nfconfig.py:100`), which the user sets via `--work-dir`
(`src/contig/cli.py:400`) and which merely *defaults* to `f"{runs_dir}/{run_id}/work"`
(`src/contig/cli.py:596`). The two agree only in the default case — which is why this
has never been caught.

**Cost when they disagree** (each step verified, not inferred):

1. `work.is_dir()` is false → the function returns `""` (`runner.py:1199-1200`).
2. Every regex branch in `diagnose_failure` misses, so control reaches the fallback at
   `src/contig/detect.py:454-466` → `tool_crash`, confidence **0.4**, evidence = the
   last non-empty line of `run.log`. The cliff is steep and near-total: `diagnose_failure`
   is a waterfall of substring matches over `log_text` (`detect.py:23-30`), and its
   **only** non-log signals are the exit-137 OOM check (`detect.py:88`) and the
   `e.exit is None` co-requirement on the platform rule (`detect.py:376`). So
   **exit-137 OOM is the one class that survives an empty log.** Everything else —
   `container_unavailable`/`container_pull_failed`/`disk_full` (0.9),
   `permission_denied` (0.85), `reference_mismatch` (0.85), `platform_unsupported`
   (0.7) — is unreachable.
3. `propose_patches` has no `tool_crash` branch → returns `[]`. **A recoverable run is
   not recovered.** An OOM, a missing index, a bad param, a platform mismatch all
   collapse into "unrecognized".
4. `self_heal.py:1319` files the failure to the pending corpus with that `log_text`
   as the case body (`corpus.py:107-129` → `FailureCase.log_text`, `models.py:463`)
   and `tool_crash` as a PROVISIONAL label. **Moat #2 accumulates a case that is both
   evidence-less and mislabeled** — worse than accumulating nothing.
5. **The corpus clustering silently collapses.** `cluster_failures` keys each case on
   `normalize_signature(case.log_text)` (`corpus.py:257`), which filters to lines
   carrying a salient token and hashes the result (`corpus.py:225-244`). **Every
   evidence-less case hashes to the same constant signature**, so all of them merge
   into one bogus "recurring systemic mode" cluster — the exact artifact the
   clustering exists to surface. And `corpus.py:72` replays the detector against the
   *stored* log, so an empty one can only ever grade events-only rules: the eval
   silently measures less than it claims to.

**Evidence it is real, and why it survived.** Two facts from the test surface:

- The self-heal suite has **always** run in the broken configuration: the canonical
  fixture is `_target(tmp_path / "w")` (`tests/test_self_heal.py:29-30, 38`) while
  `run_dir` is `<runs_dir>/<run_id>` — the two have never agreed.
- **No test anywhere writes a `.command.err` into a self-healed run.** Grepping
  `tests/` for `command.err` hits only `tests/test_runner.py` (four unit tests of the
  function in isolation, against a hand-built `<tmp>/work` that matches its own
  hardcoded assumption) and two unrelated names in `test_cli_reproduce.py`.

So the unit tests pass because they reproduce the bug's assumption, and the integration
tests pass because they never supply the file whose absence is the bug. **Both
directions are currently green for the wrong reason.**

**Honest framing: this is push, not demand-pull.** No user has reported it and we have
no measurement of how many runs use a custom `--work-dir`. The case rests on the defect
being *filed, verified, silent, and corpus-poisoning* — not on observed user pain.

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| The detector sees `.command.err` under any local work dir | A `self_heal_run` test writing a classifiable `.command.err` under a custom `work_dir` yields that specific class, not `tool_crash` @ 0.4. Fails today, passes after. |
| A structurally unreadable work dir says so | A remote (`s3://`) work dir produces an explicit note in `log_text`, not `""`. |
| The legitimate empty case is untouched | Every **assertion** in `tests/test_runner.py:59-101` survives verbatim; only the four call lines gain the required `work_dir` argument (M1). No assertion is weakened, retargeted, or deleted. |
| No contract drift | No change to `models.py`, `LaunchManifest`, the verdict, exit codes, bundle fields, or any **signed/persisted** payload. The one signature that changes is the internal `read_task_errors`, which has three references repo-wide (R6). Full suite green. |

Explicit non-metric: we are **not** claiming a measurable rise in real-world recovery
rate. There is no baseline to measure against (see Risks R1).

## Users & Scenarios

**Both scenarios below are ILLUSTRATIVE, not observed.** No user has reported this and
we have no measurement of custom-`--work-dir` usage (see R1). They are written to make
the failure concrete, not to imply established demand. The AWS Batch limit, by contrast,
is structural fact rather than a persona: `preflight_aws_batch` refuses a non-`s3://`
work dir outright (`nfconfig.py:119-122`).

- **Core facility / HPC operator (Contig ICP) — hypothetical.** Points `--work-dir` at fast scratch
  (`/scratch/$USER/work`) because the runs dir is on slow shared NFS. Today every
  failure on that cluster is `tool_crash`, self-heal is inert, and they cannot tell
  why. After: normal diagnosis and self-heal.
- **Cloud/Batch user — structural, not hypothetical.** `preflight_aws_batch` **requires** an `s3://` work dir
  (`nfconfig.py:119-122`), so `.command.err` can *never* be read off local disk there.
  After: they get an explicit statement of that limit instead of silence.

## Requirements

### Must-have

- **M1 — Thread the real work dir, as a REQUIRED parameter.**
  `read_task_errors(run_dir, work_dir, ...)`. The `<run_dir>/work` fallback is
  **removed**, not defaulted. *Decision reversed from the brief during self-critique:*
  M2 makes the sole production call site always pass a work dir, so a retained fallback
  would be a production-dead code path preserved only to keep four tests unmodified —
  and an unreachable "look somewhere else" branch is exactly where the next version of
  this defect would hide. Cost: four one-line edits in `tests/test_runner.py`. The
  function can no longer silently look in the wrong place.
- **M2 — Use it at the one call site.** `self_heal.py:1310` passes
  `current_target.work_dir`. `current_target` is in scope (`self_heal.py:1198`) and is
  **verified stable across attempts**: the only rebinding path is `apply_patch`
  (`self_heal.py:531-626`), which `model_copy`s `resource_limits` or `backend_options`
  only — never `work_dir`.
- **M3 — Honest note for the structurally unreadable case.** A work dir carrying a URI
  scheme other than `file://` returns a one-line note naming the work dir and the
  reason, instead of `""`. Two constraints, both from existing house rules:
  - **Self-labelled, never log-shaped.** The nearest precedent is in this very
    function's caller (`self_heal.py:1279-1301`), whose comment states the rule:
    passing `""` "would file a case carrying no evidence, and log-shaped prose would
    put words in Nextflow's mouth". The note must therefore be non-empty *and*
    visibly ours (a `[contig]`-style prefix), never mimicking tool output.
  - **It must carry a salient token.** `normalize_signature` keeps only lines matching
    `_SALIENT_TOKENS` (`corpus.py:207-219`: `error`, `fail`, `cannot`, `unable`,
    `no such`, `missing`, `denied`, …). A note containing one gives remote-work-dir
    cases their **own** cluster; a note without one is filtered out and those cases
    rejoin the constant empty-signature blob described in Problem §5. This is a
    deliberate wording requirement, not incidental phrasing.
- **M4 — Preserve the legitimately-empty case.** A **local** work dir that does not
  exist returns `""`, unchanged. This is the common, correct case: a run that fails
  before any task starts (bad param, container pull failure) never creates the work
  dir at all. `tests/test_runner.py:73-76` asserts this by **exact equality**; its
  assertion is preserved verbatim, only its call gains the new argument.
- **M5 — The missing end-to-end test.** A `self_heal_run` test that writes a
  `.command.err` under the target's actual `work_dir` and asserts the diagnosis is the
  specific class. This is the coverage whose absence let the bug survive.
- **M6 — Neither half of the `log_text` expression may raise.** `self_heal.py:1310` is
  `read_run_log(run_dir) + "\n" + read_task_errors(...)`; an exception from *either*
  side aborts diagnosis, and a crash **during diagnosis** destroys the very failure
  record we are trying to capture. Both hazards are pre-existing; both are guarded here
  because this slice is already editing this expression.
  - **`read_task_errors`** — a `.command.err` that exists but cannot be read
    (permissions) is skipped rather than propagating `OSError`/`PermissionError`
    (`runner.py:1208`, a bare `read_text` inside the loop).
  - **`read_run_log`** — `runner.py:1185-1188` calls `read_text()` with **no
    `errors="replace"`**, unlike `read_task_errors` (`runner.py:1209`), so a non-UTF-8
    `run.log` raises `UnicodeDecodeError`. Fixed by adopting the same tolerance its
    sibling already has. *This corrects an earlier claim in this PRD that `read_run_log`
    needed no change: it has no work-dir bug, but it is not safe.*

### Should-have

- **S1** — The note is greppable: one fixed stem so occurrences can be counted across
  runs without new telemetry (the freshness-guard precedent, `CAPABILITY_ROADMAP.md`
  C8 freshness slice).
- **S2** — `file://` is normalized and read as the local path it names, not treated as
  remote.

### Out of scope

- Any attempt to **fetch** remote task logs (S3/GCS clients, new dependencies).
  Contig is stdlib-only on this path and no network read is warranted for a note.
- A launch-time warning when the work dir is remote (touches the launch path; this is
  a read-path slice). *User-declined in interview.*
- Identifying or relabeling pending-corpus cases already captured with a wrong
  `tool_crash` label. *User-declined in interview; corpus curation is a separate concern.*
- Any `detect.py` change, including to the `tool_crash` evidence rule.
- Snakemake (no Nextflow work dir concept on that path).
- Persisting `work_dir` into `LaunchManifest` — deliberately absent
  (`models.py:408-415`) and staying absent.
- Fetching or authenticating against remote object stores to *count* or *list* task
  files. The remote branch is a pure string decision; it performs no I/O.

## Technical Considerations

**Where it sits.** Purely the *detect* input of the orchestrate → run → **detect** →
diagnose → repair loop (ARCHITECTURE §5.1-5.2). It changes what the detector can *see*,
never what it *decides*.

**The remote rule (confirmed).** Treat `<scheme>://` as remote for any scheme except
`file://`. Chosen over `s3://`-only because it needs no edit the day a `gs://` or
`az://` backend lands, and over "any non-existent dir" because that collapses M4's
legitimate empty case and breaks an existing exact-equality assertion.

**Note placement — a deliberate reversal, recorded.** The interview option proposed
placing the note *first* so `detect.py:457-459`'s `[-1:]` rule would not select it.
That is not achievable without reordering the call site, because the concatenation is
`read_run_log(...) + "\n" + read_task_errors(...)` — whatever the latter returns lands
last. **On inspection, last is the correct place.** In the remote case the most accurate
possible `tool_crash` evidence line *is* "the task errors could not be read because the
work dir is remote", rather than an arbitrary trailing `run.log` line. So the note is
allowed to become the evidence line, deliberately. Reordering the concatenation was
considered and **rejected**: it would change the evidence line for *every* run
(currently the task error's last line, which is strictly more informative than
`run.log`'s), a regression far wider than this slice.

**Reproducibility / verification impact: none.** Read-path only. No verdict, exit code,
QC check, bundle field, or signed payload changes. Not a signature break.

**Determinism.** The note is a pure function of the work-dir string. No clock, no
filesystem call needed for the remote branch.

## Risks & Open Questions

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | **Push, not demand-pull.** May change nothing for any real user. | Med | Recorded honestly rather than mitigated. The corpus-poisoning path (Problem §4) is the part that has value even at zero current users. Revisit trigger: the first real custom-work-dir failure report. |
| R2 | The note becomes the `tool_crash` evidence line. | Low | **Accepted by design** — see "Note placement" above. It only fires for a remote work dir; the local empty case is unchanged. |
| R3 | A relative `work_dir` resolves against a different cwd than `run_dir`. | Low | Default is `f"{runs_dir}/{run_id}/work"`, a relative string resolved the same way `run_dir` is. Pin with a test that the default path stays byte-identical. |
| R4 | Self-graded: we write the fixture for the class we make reachable. | Low | Inherent to the repo's synthetic-fixture discipline; state it in the CHANGELOG as prior slices do. |
| R5 | Fix is reasoned, not observed — no real Nextflow, no real Batch run in CI. | Med | Disclose. Consistent with every prior C2/C8 slice; a real-run smoke stays a manual gate. |
| R6 | The `read_task_errors` signature change breaks an unknown caller. | Low | Grepped: exactly three references repo-wide — `self_heal.py:69` (import), `self_heal.py:1310` (call), `tests/test_runner.py`. Not exported in any public API surface, not referenced by `dashboard/`. |
| R7 | Edge inputs to the remote rule: `""`, a Windows path (`C:\work`), a trailing-slash URI. | Low | Key the rule on the substring `://`, never a bare `:`, so a drive letter stays local; `""` is local-and-absent → `""` per M4. All three pinned by tests. |
| R8 | M6's permission guard silently swallows a real read error. | Low | Skip-and-continue matches the function's existing tolerance (`errors="replace"` at `runner.py:1208`); it degrades one task's text, never the whole diagnosis, and the run still classifies on whatever else was readable. |

**Open questions (non-blocking):**

1. Exact note wording — settle during implementation against the house "honest
   give-up" style.
2. ~~Should `read_run_log` take the same treatment? … Confirmed no change.~~
   **CORRECTED.** `read_run_log` is right about the *path* (it reads
   `<run_dir>/run.log`, which Contig itself writes), so the work-dir bug does not
   apply to it. But it is **not** safe: `runner.py:1185-1188` calls `read_text()` with
   **no `errors="replace"`**, unlike `read_task_errors` (`runner.py:1209`). A
   non-UTF-8 `run.log` therefore raises `UnicodeDecodeError` out of the *same*
   `self_heal.py:1310` expression, killing diagnosis exactly as M6's hazard would.
   **RESOLVED: folded into M6** — `read_run_log` adopts the `errors="replace"` its
   sibling already has.

## Effort

Small: one function signature + body in `runner.py`, one call-site argument in
`self_heal.py`, four one-line test-call edits, and ~7 new tests. No new module, no new
dependency, no `models.py` change.

## Acceptance (test-first)

1. RED: `self_heal_run` with a custom `work_dir` containing a classifiable
   `.command.err` → asserts the specific failure class; fails today (`tool_crash`).
2. Remote `s3://` work dir → `read_task_errors` returns the note; the note names the
   work dir; nothing is globbed.
3. Local absent work dir → returns `""` exactly (M4).
4. The four existing `tests/test_runner.py` assertions are preserved **verbatim**;
   only their call gains the required `work_dir` argument. No behavioral test changed.
5. `file://` work dir → read as the local path it names.
6. Edge inputs pinned: `""`, `C:\work` (local, not remote), trailing-slash URI.
7. Neither half of the `log_text` expression raises (M6): an unreadable `.command.err`
   is skipped, and a non-UTF-8 `run.log` decodes with replacement.
8. `tests/test_self_heal.py:301` (`assert pending[0].log_text`) is **strengthened**: it
   asserts truthiness only, so the M3 note would satisfy it vacuously. It must assert on
   real captured content instead.
9. Full suite green; no `models.py` diff; `read_task_errors` has no production-dead
   branch.
