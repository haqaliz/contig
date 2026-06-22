# PRD: In-run controls, self-heal confirm gate, eval-history trends

Status: approved, in build. Owner: orchestrator + agent team. Target branch: master (commit and push per feature as it goes green).

Three features built in one pass. On-disk contracts are pinned so the engine
(Python) and dashboard (Next.js) streams build in parallel against one interface.

## Decisions (locked with the user)

1. Cancel AND Resume both ship this pass. Resume continues the same run id with
   Nextflow -resume against the cached work dir.
2. The self-heal confirm gate makes BOTH needs_confirmation and destructive
   patches approvable: they pause the run for explicit human approve or reject;
   safe patches keep auto-applying as today. Nothing risky auto-applies.
3. A paused run waits in an "awaiting approval" state with a configurable timeout
   (default 1800 seconds); on timeout it skips the patch and stops (conservative).
4. Eval snapshots are recorded by `contig eval-detector --snapshot` AND
   automatically on corpus-promote, appended to a committed history file
   (src/contig/data/eval_history.jsonl). The trend is shown on /eval.

## Non-goals

- No Layer-1 work. No new compute backend.
- apply_patch stays bounded: it already applies resource bumps; this pass also
  applies approved "param" patches (merged into params) and "env" patches. The
  "reference" and "code" kinds remain re-run-only when approved (record the
  approval and re-run; do not synthesize a code edit). Note this in the outcome.

---

## Shared run lifecycle states (status.json `state`)

`running` -> (`awaiting_approval` <-> `running`)* -> `finished` | `error` | `cancelled`

- `awaiting_approval`: the self-heal loop is paused on a gated patch (NEW).
- `cancelled`: a human stopped the run via cancel (NEW).
- `interrupted` stays a DASHBOARD-DERIVED state (status says running but the pid
  is dead); it is never written to disk.
- The dashboard `RunState` union gains `cancelled` and `awaiting_approval`.

## Contract A: cancel (engine writes terminal state)

`contig cancel <run-id> [--runs-dir]`: read status.json; if `running` or
`awaiting_approval` and the pid is alive, send SIGTERM to the PROCESS GROUP
(runs are spawned detached, so pgid == pid; `os.killpg(os.getpgid(pid), SIGTERM)`
reaps the Nextflow/Java children), wait briefly, SIGKILL if still alive, then
write status.json `state="cancelled"` with `finished_at`. If the run is not
active, exit non-zero with a clear message (nothing to cancel).

## Contract B: resume (engine re-runs the same run id with -resume)

`contig resume <run-id> [--runs-dir]`: read runs/<id>/launch.json (the manifest
from the previous pass), rebuild the exact invocation, and re-run the SAME run id
in the SAME run dir with Nextflow -resume so cached completed tasks are reused.
self_heal_run gains a `resume: bool = False` param: when true, the FIRST execute
also passes -resume (today only retries do). Valid for `cancelled` or
`interrupted` runs. status.json goes back to `running` and finalizes normally.

## Contract C: confirm gate (engine <-> human, file based)

When the loop has no `safe` patch but a gated patch exists (today it stops with
"stopped_for_confirmation"), it instead pauses:

1. Write `runs/<id>/pending_approval.json`:
   `{run_id, attempt, requested_at, timeout_sec, diagnosis:{failure_class,
   root_cause,confidence}, patch:{kind,risk,rationale,operation,expected_signal}}`.
2. Write status.json `state="awaiting_approval"`.
3. Poll for `runs/<id>/approval.json` up to `timeout_sec`:
   `{decision:"approve"|"reject", decided_at, by?}`.
   - approve: apply_patch(target, patch), record RepairStep outcome
     `approved_and_retried`, delete pending_approval.json, status back to
     `running`, continue the loop (re-run).
   - reject: record `rejected_by_user`, delete pending_approval.json, finalize
     and stop.
   - timeout: record `approval_timed_out`, delete pending_approval.json, finalize
     and stop.

`contig run` gains `--auto-approve` (apply gated patches without waiting, for
non-interactive/CI) and `--approval-timeout SEC` (default 1800). self_heal_run
gains `auto_approve: bool=False` and `approval_timeout: float=1800`.

`contig approve <run-id> [--reject] [--runs-dir]` writes approval.json.

NEW RepairStep outcomes: `approved_and_retried`, `rejected_by_user`,
`approval_timed_out`. apply_patch extended (TDD) to apply approved `param`
patches (merge `operation` into params) and `env` patches, in addition to the
existing `resource` bump.

## Contract D: eval history (engine appends; dashboard reads)

`src/contig/data/eval_history.jsonl`, one `EvalSnapshot` per line:
`{timestamp, corpus_size, corpus_sha, accuracy, per_class:{<class>:{support,
predicted,correct,precision,recall}}, contig_version}`.

- `contig eval-detector --snapshot` runs the eval and appends a snapshot.
- `contig eval-detector --history [--json]` prints the trend (accuracy over time,
  per-class deltas).
- `corpus-promote` auto-appends a snapshot after a successful promote (eval the
  golden corpus, append).
- timestamp is generated in the CLI (datetime.now(timezone.utc)); corpus_sha is
  sha256 of the corpus file so a snapshot is tied to a corpus version.

## Contract E: dashboard reads + write-through

- `RunState` adds `cancelled`, `awaiting_approval`. getRunState reads them from
  status.json (`awaiting_approval`/`cancelled`), pid-liveness logic unchanged for
  `running`.
- getPendingApproval(id) reads pending_approval.json (null if absent).
- getEvalHistory() reads eval_history.jsonl.
- Cancel/Resume/Approve dashboard APIs SHELL OUT to `contig cancel|resume|approve`
  (CONTIG_DISPATCH_CMD), validating the run id (charset, no leading dash), exactly
  like the existing dispatch routes. No direct process control from Next.

---

## Feature 1: In-run controls (Cancel + Resume)

Engine: `contig cancel`, `contig resume` (+ self_heal_run `resume` param), status
states `cancelled`. Dashboard: a Cancel button on the running/awaiting view; a
"Run cancelled" view with a Resume button; an "interrupted" run also offers
Resume. APIs `/api/runs/[id]/cancel` and `/api/runs/[id]/resume` shell the CLI.

## Feature 2: Self-heal confirm gate

Engine: pending_approval.json + approval.json poll + timeout + apply_patch
extension + `contig approve` + run flags. Dashboard: when status is
`awaiting_approval`, the live self-heal feed shows the proposed patch (kind, risk,
rationale, diagnosis) with Approve / Reject; a `destructive` patch requires a
second confirm before Approve fires. POST `/api/runs/[id]/approve` shells
`contig approve`.

## Feature 3: Eval-history trends

Engine: EvalSnapshot model + history append/load, `--snapshot`/`--history`, auto
on promote. Dashboard: /eval gains an accuracy-over-time trend (inline SVG, no new
chart dependency) plus a snapshot table with per-class deltas.

---

## Verification

- Engine: strict TDD (RED before GREEN). Full `uv run pytest` green (currently 316).
  Cancel/approve tests must not spawn real Nextflow: test the kill/decision logic
  against fixture status.json/pending_approval.json and an injected clock/timeout.
- Dashboard: `npx tsc --noEmit` + `npm run lint` clean; Playwright green with new
  fixtures (awaiting_approval run, cancelled run, eval_history.jsonl). Use
  `"pid": 1` for fixtures that must read as alive.
- Cross-layer: confirm the engine sidecar schemas match what the dashboard reads.

## Style / security constraints (carried)

- No em dash, en dash, or hyphen-as-pause anywhere (code, comments, docs, commits).
- Any user value reaching the CLI is validated (charset, no leading dash) and
  passed as `--opt=value` with a `--` terminator before positionals.
- Cancel/resume/approve dashboard routes validate the run id and shell the CLI;
  no direct kill/spawn from Next. Approving a destructive patch needs a second UI
  confirm.
