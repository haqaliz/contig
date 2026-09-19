# PRD — C9. Jev calibrated triage (BYOK, optional)

**Status:** prioritized next · owner demand-pull 2026-09-19 · **not started**
**Capability:** see `docs/technical/CAPABILITY_ROADMAP.md` → C9.

---

## Problem

The verified verdict (concordance, plausibility, structural checks) and the self-heal
loop are the trustworthy core, and they are expensive. At scale we cannot run every deep
check or attempt every self-heal with equal priority. We want a cheap, *calibrated* way to
decide which QC anomalies and step failures are worth the expensive deep check or a
self-heal attempt, and in what order — without letting a cheap cloud model near the
verdict or near raw reads.

## Approach (guardrail-preserving)

Introduce Jev (TypeSafe's System One decision model — typed Choice/Score/Bool with a
calibrated 0–1 confidence, ~150 ms, ~100× cheaper than an LLM) as a **triage/router over
run metadata only**:

- It **orders and pre-screens** QC-anomaly deep checks and self-heal attempts.
- It **never** sets a `contig verify` verdict, promotes a check to PASS, or overrides
  concordance/plausibility. (Guardrails: no Layer-1 authoring; no correctness
  over-claiming; UNVERIFIED is never PASS.)
- **BYOK, off by default.** Enabled only when the user sets **`CONTIG_JEV_KEY`** (their own
  key — never a founder/proxied key). Absent ⇒ no triage, no network, exit unchanged.
- **No raw-read egress.** Sends only **numeric QC metrics and metadata** — the class
  already allowed to leave the machine (Ti/Tv, duplication rate, mapping rate, error
  signatures, sizes/hashes) — **never raw reads, FASTQs, BAMs, or VCFs.**
- **Shadow mode is the default** when a key is present: run everything, log Jev alongside,
  until the calibration ledger earns a tighter budget.

## Requirements

**Must**
- `Triage` seam (injectable) with `JevTriage` + `NullTriage` default.
- Prioritization of QC-anomaly deep checks and self-heal ordering by Jev confidence,
  behind a budget knob.
- Calibration ledger: Jev confidence per triaged run/step vs the verdict the check produced.
- Disclosed, whitelisted metric/metadata egress payload; assertable in a test.

**Should**
- Budget as top-N-least-confident or a confidence threshold.
- A `manual`-marked live-call test for owner smoke-checks (BYOK).

**Won't (this slice)**
- No verdict authority for Jev, ever.
- No default-on behavior; no bundled/proxied key.
- No raw-read egress under any flag.

## Acceptance (test-first)

1. Triage on vs off ⇒ **identical verify verdicts** on the checks that ran.
2. Absent `CONTIG_JEV_KEY` ⇒ no-op, no network call, exit unchanged.
3. The Jev request carries only whitelisted metrics/metadata; a raw-read field never
   appears — asserted on the constructed payload.
4. Jev stubbed; deterministic, no network in CI. Live call is `manual`-marked, owner-run.

## Eval data captured

The **calibration ledger** folds into the C6 eval flywheel: does Jev's confidence actually
predict a real plausibility/concordance failure on real runs? Reliability curve, ECE, and
the decision-relevant number — at the chosen threshold, how many real failures were
deprioritized. Compounds the moat and keeps the vendor's calibration claim honest.

## Dependencies

C1/C3 (a real verified verdict to triage toward and calibrate against), C6 (the eval
flywheel, where the ledger lives). Shipped — **unblocked**.

## Honest limits

Triage only ever *saves compute/attention*, never *adds coverage*: a deprioritized check
that never runs is UNVERIFIED, never PASS. Jev's calibration is a vendor claim until the
ledger measures it.
