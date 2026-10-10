## C9. Jev calibrated triage (BYOK, optional)  ·  owner demand-pull 2026-09-19  ·  **prioritized next**

**Why it is leverage.** It is *not* the moat — it protects it. The verified verdict
(concordance, plausibility, structural checks) and the self-heal loop are the
trustworthy-but-costly core. Jev (TypeSafe's "System One" decision model — typed
Choice/Score/Bool answers with a **calibrated** 0–1 confidence, ~150 ms, ~100× cheaper than
an LLM) is a cheap **triage/prioritization** signal over run *metadata*: which QC anomalies
and step failures are worth the expensive deep check or a self-heal attempt, and in what
order. A router over metrics, never a determination about biology.

**The line that must not move.** Guardrails hold: **no Layer-1 authoring, no correctness
over-claiming, UNVERIFIED is never PASS.** Jev never sets a `contig verify` verdict, never
promotes a check to PASS, never overrides concordance/plausibility. It orders attention and
pre-screens; the verdict stays the execution-grounded check. Verify verdicts with triage on
and off must be **identical on the checks that ran** — enforced by a test.

**BYOK, off by default, no raw-read egress.** Jev is a cloud API and the
**no-raw-read-egress** guardrail is absolute. So: opt-in via **`CONTIG_JEV_KEY`** (the user's
own key, never a founder/proxied key); off by default (absent ⇒ no triage, no network, exit
unchanged); and it sends only **numeric QC metrics and metadata** — the class already allowed
to leave the machine (Ti/Tv, duplication rate, mapping rate, error signatures, sizes/hashes)
— **never raw reads, FASTQs, BAMs, or VCFs.** What is sent is named in the docs and asserted
on the constructed payload in a test.

**What we build:**
- A `Triage` seam (injectable) with a `JevTriage` implementation and a `NullTriage` default.
- Prioritization of QC-anomaly deep checks and self-heal ordering by Jev confidence, behind
  a budget knob.
- The calibration ledger (below).

**Acceptance (test-first):**
- Triage on vs off ⇒ **identical verify verdicts** on the checks that ran.
- Absent `CONTIG_JEV_KEY` ⇒ no-op, **no network call**, exit unchanged — asserted on the
  constructed request/env.
- The Jev request carries only whitelisted metrics/metadata; a raw-read field never appears
  — asserted on the constructed payload.
- Jev stubbed; deterministic, **no network in CI**. A live call is `manual`-marked, owner-run.

**Eval data captured:** the **calibration ledger** — Jev's confidence on each triaged
run/step vs the verdict the execution-grounded check later produced. It folds straight into
the C6 eval flywheel and is pure Contig: does Jev's confidence actually predict a real
plausibility/concordance failure on real runs (reliability curve, ECE, and — at the chosen
threshold — how many real failures were deprioritized)? It compounds the moat and keeps the
vendor's calibration claim honest.

**Dependencies:** C1/C3 (a real verified verdict to triage toward and calibrate against), C6
(the eval flywheel, where the ledger lives). Shipped — this capability is **unblocked**.

**Honest limits:** triage only ever *saves compute/attention*, never *adds coverage* — a
deprioritized check that never runs is UNVERIFIED, never PASS. Jev's calibration is a vendor
claim until the ledger measures it; the safe default when a key is present is **shadow mode**
(run everything, log Jev alongside).

---

## Sequencing summary
