# Understanding — `qc_anomaly` verdict trigger (Phase 2 dig)

Date: 2026-07-28 · Branch: `feat/qc-anomaly-verdict-trigger/aliz`
Source: `docs/planning/_card/issue.md` (inline brief from `/contig-next`)

Four read-only agents mapped the verdict path, the self-heal loop + detector, the C6 eval
machinery, and the `no_progress` slice as precedent. Everything below is cited to code.

---

## 1. What the work is really asking

Make `qc_anomaly` — the last `FailureClass` literal (`models.py:279`) that no code path can
ever produce — reachable, by connecting the QC verdict to the self-heal loop.

**Verified: `qc_anomaly` is genuinely dead.** No branch in `detect.py` emits it, no branch in
`repair.py` patches it, it appears in **zero of 25** training-corpus cases
(`data/detector_corpus.jsonl`), and its single held-out case has been misclassified in **all
seven** recorded trend points (`data/holdout_history.jsonl`: `predicted: 0`, `recall: 0.0`,
v0.22.0 → v0.48.0). `cli.py:2683` documents it as structurally unreachable.

---

## 2. ⚠️ The brief's stated rationale is WRONG on the mechanism (verified, twice)

The `no_progress` PRD and `CAPABILITY_ROADMAP.md:1074` defer `qc_anomaly` because *"its honest
trigger is the verdict object, not log text (**QC runs at `_finalize`, not as a pipeline
step**)"*.

The second half is false:

- **`_finalize` never computes QC.** `self_heal.py:1244-1323` contains no `_discover_qc` /
  `evaluate_run_qc` call, directly or transitively. It only *appends* one conditional
  `reference_harmonized` breadcrumb to an already-populated list (`self_heal.py:1307`).
- **QC is computed inside `run_pipeline`, on every attempt** — `runner.py:1223`,
  `qc_results=_discover_qc(run_dir, assay)`, gated only on `artifact_path.exists()`,
  **before** the `returncode != 0` check (`runner.py:1230`). Success and failure alike.

**The real reason `qc_anomaly` can't reuse the `no_progress` pattern is different and
sharper:** `diagnose_failure` is called from exactly one place — the
`except PipelineExecutionError` branch (`self_heal.py:993`) — and a QC-FAIL run **never raises
that exception**. It returns normally with `returncode == 0`. The gap is not "QC happens too
late to see"; it is **"the success path has no diagnosis call at all."**

This correction belongs in the PRD and in `CAPABILITY_ROADMAP.md` — the stale rationale should
not be inherited silently.

---

## 3. The precise trigger condition

`RunRecord.verdict` (`models.py:373-385`) checks event success **first**:

```python
@computed_field
@property
def verdict(self) -> Verdict:
    if not RunSummary.from_events(self.events).succeeded:
        return "fail"
    if not self.qc_results:
        return "unverified"
    return overall_verdict(self.qc_results)
```

So the QC-only FAIL condition is exactly:

> `RunSummary.from_events(record.events).succeeded is True`
> **AND** `overall_verdict(record.qc_results) == "fail"`

`overall_verdict` (`models.py:85-111`) already filters `informational=True` results out of the
severity reduction, so a verdict-neutral check can never trip this.

**Insertion point:** between `self_heal.py:984` (the `run_pipeline` return) and `:985` (the
`return _finalize(...)`), which today are adjacent with nothing in between.

---

## 4. 🔑 THE TWO DOORS — and only one of them moves the eval number

This is the central finding and the decision the PRD must make explicitly.

| | **Door A — log-text needles** | **Door B — verdict object** |
|---|---|---|
| Trigger | A pipeline QC-gate **step that FAILED** | A **zero-exit** run whose QC reduces to FAIL |
| Shape | `events: [{process: "MULTIQC_QC_GATE", status: "FAILED", exit: null}]` + log text *"QC gate rejected the run: MultiQC duplication-rate metric (92%) breached…"* | No exception, no failed event, no log text |
| Today classifies as | `tool_crash` (catch-all, `detect.py:387`) | never diagnosed at all |
| Mechanism | new needle tuple in `detect.py` | new check in `self_heal.py` success path |
| **Moves `eval-guard` 0.923 → 1.0?** | **YES** | **NO** |
| Is it the product-real gap? | No — third-party QC gates | **Yes** |
| Risk | foreign-text needles nothing constrains (the `no_progress` trade) | none of that kind |

**The honest correction to the pick I made:** the 13/13 headline is achievable **only through
Door A**. The held-out corpus contains no structural/zero-exit case, so shipping Door B alone
leaves `eval-guard` at 0.923. The two must be argued separately — **the eval number must not
be allowed to justify the needle rule.**

Door A's needles would be third-party wording ("QC gate rejected", "duplication-rate metric",
"breached … threshold"). The `no_progress` slice's own committed comment (`detect.py:39-54`)
is the standard to be held to: *"every phrase added here is false-positive surface charged
against every diagnosis Contig makes."* Door A cannot meet that slice's justification — its
needles would be phrases **Contig never emits**, so the "our own wording is ordinary English"
defence is unavailable. It would be a straight bet on foreign text.

---

## 5. The repair side: a retry is PROVABLY useless (so give-up is the honest outcome)

Verified, not assumed:

- `-resume` is appended to the argv with **no cache invalidation** (`runner.py:1116-1117`);
  grep for work-dir clearing / `.nextflow/cache` logic returns **zero hits** — Contig has no
  mechanism of its own to invalidate Nextflow's task cache.
- A QC-FAIL run has `RunSummary.succeeded == True` by definition — **every task exited 0**, so
  every task is cache-valid.
- Therefore a bare retry re-executes **nothing**, reproduces byte-identical outputs, and
  `overall_verdict` re-derives **identically**.

This is the sharp contrast with `no_progress`, whose retry is defensible despite an all-hit
cache because a stall's cause (wedged mount, transient hang) is plausibly gone next attempt.
Here the cause is *in the data*, and nothing about a retry touches it.

**Consequence — the honest outcome falls out of existing machinery for free.**
`propose_patches` has no `qc_anomaly` branch → returns `[]` → `self_heal_run`'s `not patches`
path (`self_heal.py:1015-1025`) records `RepairStep(patch=None, outcome="gave_up")` and
finalizes. No new repair code, no retry, no loop-termination hazard. A `kind="retry"` patch
here would be a dressed-up recovery and must not be written.

---

## 6. What does NOT change (contract boundaries to pin as tests)

- **Exit code.** `cli.py:743-744` already exits 1 when events fail (unconditional);
  `cli.py:745-747` exits 1 on a FAIL verdict **only** under `--fail-on-verdict` (v0.36.0).
  A QC-only FAIL exits **0** by default and must continue to.
- **Lifecycle event.** `_finalize` emits `finished`/`failed` from
  `RunSummary.from_events(...).succeeded` — for a QC-only FAIL that stays `finished`. Routing
  through a give-up path must not flip it to `failed`.
- **`record.verdict`** is a computed field; it is already `"fail"` today. This slice does not
  change any verdict, band, or threshold — it changes whether the FAIL is *diagnosed*.

---

## 7. Open questions for the PRD interview

1. **Which door(s)?** Door B alone (honest, no eval move), Door A alone (eval move, foreign
   needles), or both-argued-separately.
2. **What is Door B actually worth**, stated plainly? Candidates: the class becomes reachable;
   the FAIL lands in `repair_history` / `repair_progress.jsonl` so the dashboard and the
   corpus see a *diagnosed* event instead of a silent green run; the architectural link
   "verify feeds self-heal" exists for the first time. Is that enough for a slice?
3. **Corpus capture.** The pending-corpus write (`self_heal.py:997-1007`) sits on the
   exception path. Should a QC-FAIL run be captured as a `FailureCase` too (moat #2 eval
   data), and if so under what label — it has no failure log text.
4. **`heal-guard` coverage is not free.** `HealScenario`/`AttemptSpec`
   (`models.py:533-560`) replay `status`/`exit`/`log_text` only, and `_discover_qc` finds
   nothing in the scripted harness → any scenario reduces to `unverified`, never `fail`.
   Covering Door B needs a new seam to inject QC results (a `models.py` + `heal.py` change +
   `corpus_sha` refreeze). In scope or deferred?
5. **Detector-corpus honesty.** If Door B ships, should a *structural* `qc_anomaly` case be
   added to the training/held-out corpora at all? Neither corpus can currently represent a
   zero-exit case — `expected_class` is scored from `(events, log_text)` only.
6. **Does `diagnose_failure` get a new parameter, or does the success path synthesize the
   `Diagnosis` directly?** The `Detector` type is
   `Callable[[list[TaskEvent], str], Diagnosis]` (`detect.py:20`); widening it touches the
   LLM detector and every injection site. Synthesizing in `self_heal.py` avoids that.

---

## 8. Guardrail check (`CLAUDE.md`)

- **Layer 2 ✓** — pure run/verify/self-heal wiring; no NL→workflow surface anywhere near it.
- **Founder's edge ✓** — no wet-lab/clinical credentials, no proprietary data, no new bands or
  biological claims. This slice adds **no** QC threshold and makes **no** clinical judgement.
- **Moat ✓** — hardens the verify↔self-heal link and captures eval data; gets better as models
  improve (a better model adjudicates *why* QC failed), never redundant.
- **Test-first ✓** — required, per repo standing discipline.

## 9. Honest limits to carry into the PRD

- Any `eval-guard` movement is **partly self-graded** — we would be scoring a class whose
  held-out fixture we wrote (the `no_progress` slice recorded exactly this about itself).
- **Push, not demand-pull** — no design partner asked for this; it closes a documented
  taxonomy gap. The frequency of real QC-FAIL-on-green runs is **unmeasured**.
- Door B's value is **architectural and telemetric**, not a recovery. It recovers nothing, by
  design, and the PRD must say so rather than implying self-heal got stronger.
