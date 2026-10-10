# Spec — Aspect: `wiring`

Slice of the PRD: active-mode flags and their refusals, the two wrap sites
(qc_anomaly ledger-only; verify-time concordance dispatch skip surface), heal-scenario
threading for CI determinism, the R4 skippable-set predicate, and the verdict-identity
invariant tests.

## In-scope (PRD R3, R4, R5, S1)

- `--triage-active` (bool, off) + `--triage-threshold` (float 0-1, default 0.5,
  reasoned-uncalibrated) on `contig run` and `contig verify`; threshold without
  active and active without `CONTIG_JEV_KEY` are refused naming the env (the
  `_validate_stall_flags` companion-refusal pattern, `cli.py:367-399`).
- `Triage` kwarg on `self_heal_run` (default `NullTriage`, precedent `propose`/
  `sleeper`, `self_heal.py:1186-1201`), threaded through `run_heal_scenario`
  (`heal.py:188-246`) so heal-guard scenarios stay deterministic, and into the
  `contig verify` path (`cli.py:1998-2380`) at the concordance dispatch
  (`:2188-2232`).
- qc_anomaly site (`self_heal.py:1250-1319`): **ledger-capture only** — the seam is
  consulted after the trigger fires; the trigger itself always fires and its
  Diagnosis/pending-corpus capture are untouched.
- verify-time site: **the only active-mode skip surface**. A dispatched concordance
  evaluator is skipped iff (a) active mode AND (b) Jev confidence < threshold AND
  (c) the check passes the R4 predicate (skippable = `kind == "concordance"` or no
  `fail_*` bound). A skipped check renders as an honest UNVERIFIED result
  (`kind="concordance"`, message naming the threshold + skip reason) — never absent,
  never PASS, and an appended ledger row (ledger aspect consumes the row).
- R4 predicate as a pure exported function with a test enumerating the skippable set
  by walking the shipped rule packs' band dicts (`rule_pack.py:545-564`).
- Verdict-identity invariant tests: triage off vs shadow ⇒ byte-identical behavior;
  triage on ⇒ identical verdicts on the checks that ran.

## Out-of-scope

The seam module internals (aspect `seam`), the ledger sidecar/stats (aspect `ledger`),
self-heal attempt ordering across `max_attempts`, any change to the R4-ineligible
checks, any verdict-authority semantics.

## Acceptance (test-first)

1. Heal-guard scenarios unchanged: outcome-match 1.0 over the frozen set with the
   seam injected (`NullTriage`), baselines unmoved.
2. Triage off vs shadow ⇒ identical verdicts and identical bytes on the checks that
   ran (existing verify/heal test suite green, plus a dedicated identity test).
3. Active mode skips only R4-predicate checks; a FAIL-capable check (`ts_tv` FAIL
   band, `somatic_variant_count fail_below: 1`) is pinned never-skippable by test.
4. Skipped check ⇒ UNVERIFIED result with reason; the qc_anomaly trigger output is
   byte-identical with triage on/off.
5. Flag refusals: threshold-without-active, active-without-key (exit non-zero,
   naming `CONTIG_JEV_KEY`), threshold bounds validation.
6. `contig run`/`verify` defaults unchanged (no flags) behave byte-identically.

## Dependencies & sequencing

Second aspect (after `seam`). No `models.py` change; no new dependency; stdlib only.

## Open questions / risks

- Verify-time dispatch runs exactly one evaluator per invocation (mutually exclusive
  flags) — "skip" is therefore per-invocation, not per-check-batch; the spec's
  granularity is one decision per verify invocation. Confirmed for slice 1.
- The R4 predicate needs a stable rule→`QCResult` mapping (match by check name in
  the shipped packs); enumerate explicitly in the test so a new FAIL band is a
  deliberate act.