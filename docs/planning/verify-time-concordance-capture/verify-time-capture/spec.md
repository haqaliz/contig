# Aspect spec: verify-time-capture

Parent PRD: `../prd.md`. Single aspect for this slice (small, cohesive — the whole PRD).

## Problem slice & user outcome

`contig verify --concordance-*` computes germline/RNA-seq/single-cell concordance
checks but the pre-band inputs of those checks are never captured into the C6 eval
corpus — the last R4a deferral. After this aspect, every concordance invocation that
produces results appends one pending `VerificationCase` to
`<runs_dir>/pending_verify_corpus.jsonl`, promotable via the existing
`verify-case-promote`, with the signed bundle and all four guard baselines untouched.

## In scope

1. `capture_metrics` out-params on `evaluate_concordance`, `evaluate_count_concordance`,
   and `evaluate_sc_count_concordance` (the `somatic_concordance.py:126-149` precedent;
   populated on BOTH the normal and too-few-shared paths; additive, absent → byte-identical).
2. A verify-time capture hook in `verify()` immediately after the six-way dispatch
   (cli.py:1650-1651), gated on "results exist" (non-empty `concordance` list),
   always-on, no flag.
3. Case shape: `case_id = f"{run_id}-verify-concordance"`, `source = "pending:{run_id}"`,
   `assay` from the record, `expected_verdict = None`, inputs `{family: {"S1":
   {"value", "n_shared"}}}` where family is `concordance_genotype` (germline) or
   `concordance_spearman` (rnaseq + scrnaseq).
4. Dedupe-on-append in the verify-time writer only (skip when `case_id` already present
   in the pending file). Shared `append_verify_case` untouched.
5. Round-trip pins (capture → promote → re-derive under current thresholds → statuses
   match), a mutation-control pin (threshold change flips a stored case), and the
   output byte-stability pin (verify text/JSON output unchanged with capture active).

## Out of scope

- Scorer, holdout corpus, baselines, or any of the four guards (all unmoved by design).
- Any change to concordance verdict semantics (WARN-capped, exit-code-neutral).
- Dashboard UI; capture-time echo in verify output (nice-to-have, deferred).
- Verify-time capture for other families (all others are run-dir-derived, shipped).

## Acceptance criteria (testable)

- **AC1** `evaluate_concordance(..., capture_metrics=capture)` populates
  `capture["S1"] == {"value": <raw rate>, "n_shared": <float shared>}` on both the
  normal and the no-shared-known-GT paths; absent param → results byte-identical.
- **AC2** `evaluate_count_concordance` and `evaluate_sc_count_concordance` populate
  `capture["S1"] == {"value": <raw rho>, "n_shared": <float shared>}` on both the
  normal and the too-few-shared paths; absent param → results byte-identical
  (sc reuses the count core — one change, both inherit).
- **AC3** `contig verify <id> --runs-dir <d> --concordance-counts <m>` appends one
  `VerificationCase` line to `<d>/pending_verify_corpus.jsonl` with the exact case
  shape; verify without a concordance flag writes nothing; a non-matching assay
  (honest skip, `[]`) writes nothing.
- **AC4** Running the same verify twice appends one line (dedupe by `case_id`).
- **AC5** `verify-case-promote <case_id> --expected-verdict warn` promotes the case,
  rewrites source `pending:` → `confirmed:`, dedupes against golden, auto-snapshots.
  The scorer's re-derived status for the stored `{value, n_shared}` equals the expected
  verdict; a threshold-band flip (family_packs override) changes the re-derived status.
- **AC6** Verify text and JSON output are byte-identical with and without capture
  active (capture invisible to every user-facing surface).
- **AC7** The signed bundle is untouched: no write to the run dir on verify; all four
  guards pass bare with byte-identical baselines.
- **AC8** Suite stays green (2644 passed, 1 skipped baseline); no network, no real
  tool execution, no new dependency.

## Dependencies & sequencing

Phase 1 (out-params) before Phase 2 (hook) before Phase 3 (pins). No external deps.

## Risks specific to this aspect

- `case_id` collision with the finalize-time `f"{run_id}-verify"` case — resolved by
  the distinct `-concordance` suffix (PRD decision).
- The family-key enumeration pin (`test_verify_capture_roundtrip.py:438-464`) scans
  runner.py only — extend deliberately to cover the verify-time writer or document why
  not (should-have).
- Repeated verify of the same run — resolved by dedupe-on-append (PRD decision).
