# Card: Jev calibrated triage (C9, BYOK, optional)

Source: inline brief (no GitHub issue; from /contig-next handoff, 2026-10-10).
Owner: aliz. Type: feat. Slug: `jev-calibrated-triage`.

## Brief

Build C9 "Jev calibrated triage" from `docs/technical/CAPABILITY_ROADMAP.md`
(the C9 section, which lives on the unmerged remote branch
`origin/feat/jev-triage` at commit `888df6c` — master does not contain it):

Jev (TypeSafe's "System One" decision model — typed Choice/Score/Bool with a
calibrated 0–1 confidence, ~150 ms, ~100x cheaper than an LLM) is a cheap
**triage/prioritization** signal over run *metadata*: which QC anomalies and
step failures are worth the expensive deep check or a self-heal attempt, and in
what order. It is a router over metrics, never a determination about biology.

Slice 1 must:
- Add a `Triage` seam (injectable) with `NullTriage` as the default and a
  `JevTriage` implementation behind `CONTIG_JEV_KEY` (BYOK, off by default;
  absent key => no triage, no network, exit unchanged).
- Prioritize QC-anomaly deep checks and self-heal ordering by Jev confidence,
  behind a budget knob.
- Record a calibration ledger: Jev confidence per triaged run/step vs the
  verdict the execution-grounded check later produced. Folds into the C6 eval
  flywheel.
- Send only whitelisted numeric QC metrics/metadata — never raw reads, FASTQs,
  BAMs, or VCFs — asserted on the constructed payload in a test.
- Shadow mode is the default when a key is present: run everything, log Jev
  alongside.
- Jev never sets a `contig verify` verdict, never promotes a check to PASS,
  never overrides concordance/plausibility. Triage on vs off => identical
  verify verdicts on the checks that ran (enforced by a test).

Guardrails (CLAUDE.md): Layer 2 only; no Layer-1 authoring; no raw-read egress;
no correctness over-claiming (UNVERIFIED is never PASS); no clinical claims.
Test-first; Jev stubbed in CI (deterministic, no network); a live call is a
`manual`-marked owner-run gate. Stdlib-only posture: no new dependency
(pydantic/typer/cryptography only); follow the shipped env-gated provider seams
(`detect._selected_provider`, `extract_with_llm`, the DOI `urllib` fetch).

## Caveats from the handoff

- The C9 PRD + roadmap section live ONLY on `origin/feat/jev-triage`
  (commit `888df6c`, branched at v0.60.0, 76 commits behind master). Bring them
  into the worktree before planning; copies saved next to this card.
- No Jev/TypeSafe API surface exists anywhere in `src/contig/` — the vendor's
  request/response shape is unverified from the repo. Keep Jev behind the
  injectable `Triage` seam so absence/failure degrades to `NullTriage`.

## Reference copies (taken from origin/feat/jev-triage @ 888df6c)

- `docs/planning/_card/c9-prd-branch.md` — the branch's PRD stub.
- `docs/planning/_card/c9-roadmap-branch.md` — the branch's C9 roadmap section.
