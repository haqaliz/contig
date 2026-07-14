# Understanding: germline-plausibility-fail-severity

_Phase 2 deep-dig note. Grounded in a read-only trace of the worktree at HEAD
(origin/master). Two dig agents: verdict/exit-code path + WARN-only contract inventory._

## What the work is really asking

Give the **germline biological-plausibility** checks their first FAIL severity by adding
`fail_below`/`fail_above` bands to three rule dicts in
`src/contig/verification/rule_pack.py` (`VARIANT_RULE_PACK`): `ts_tv_ratio`,
`het_hom_ratio`, `variant_count`. Today all three are WARN-only (no `fail_*`). The bands
must be **gross-implausibility-only** engineering tripwires ("this call set is broken"),
wide enough that a legitimate WES run (Ti/Tv ~3.0–3.3) never FAILs, on the same honesty
tier as the existing `mean_coverage fail_below: 10` — never a clinical/biological claim.

## How the code actually behaves (the important corrections)

1. **Adding the band data is the ONLY functional change.** `rule_pack._status_for()`
   (`rule_pack.py:435-454`) already honors `fail_below`/`fail_above` via `.get()`;
   `evaluate()` passes the status through; `evaluate_variant_plausibility()`
   (`variant_metrics.py:151-200`) hands the germline rule dicts straight to `evaluate()`
   with **no WARN clamp**. So adding `fail_*` keys to the three dicts automatically yields
   `status="fail"` — identical to how `mean_coverage`/methylseq/scrnaseq packs already
   fail. No evaluator/plumbing change needed.

2. **The verdict reducer already handles a failing plausibility result.**
   `overall_verdict()` (`models.py:78-96`) inspects only `.status` — `if "fail" in
   statuses: return "fail"`. It does **not** special-case `kind` (structural / metric /
   concordance are equal). One failing germline plausibility QCResult drives
   `record.verdict` → FAIL. Concordance's "at most WARN" is by *construction*
   (`concordance.py` only emits warn/pass) and because the verify CLI never adds
   concordance to `qc_results` — NOT a reducer clamp. Germline plausibility results ARE
   added to `qc_results` uncapped (`runner.py:295`).

3. **⚠️ The brief's premise "reverses … never changes the verify exit code" is
   misleading.** No QC verdict changes the CLI exit code today — not even the
   already-failing did-it-run packs.
   - `contig verify` exit code: set ONLY from output drift (`verify_outputs`) + signature
     (`cli.py:953-954, 964-971`). Never reads `record.verdict`.
   - `contig run` exit code: gated on pipeline execution success
     (`cli.py:618-620`), not the QC verdict.
   So a germline plausibility FAIL surfaces in `record.verdict`, `render_run_report`,
   `render_explain`, provenance, and the dashboard — but the process exit stays 0 unless
   we add NEW wiring. **This is the central scope question for the interview** (see below).

4. **History:** the germline pack ORIGINALLY carried FAIL bands `[1.5, 3.0]` on
   ts_tv/het_hom; v0.3.0 deliberately **removed** them "until calibrated on real data"
   (`CHANGELOG.md:1386-1388`). A synthetic test `_ts_tv_range_pack()`
   (`test_rule_pack.py:126-137`) with `fail_below:1.5`/`fail_above:3.0` already models the
   scorer path. Re-adding fail bands is reinstating a removed contract with wider,
   WES-safe bands.

## Affected areas

- **Change (data):** `src/contig/verification/rule_pack.py:54-78` — add `fail_*` to the
  three germline dicts; update the WARN-capped comments (`:44-48, 51-53, 61, 69-72`).
- **Docstrings (cosmetic):** `variant_metrics.py:154, 166`.
- **Tests to update (assert WARN-only today):** `test_variant_metrics.py:242, 306, 319,
  334`; `test_rule_pack.py:178`. Plus add new RED tests for the FAIL bands.
- **Docs to sync:** `CHANGELOG.md` (new entry), `docs/technical/CAPABILITY_ROADMAP.md`
  (C3 germline rows `:432-452, 828`), `FEATURES.md:252`, and the germline planning PRDs.
- **Baseline:** `uv run pytest` → **1479 passed, 1 skipped** (from the most recent
  germline slice's PRD).

## Open questions for the interview (context can't resolve these)

- **Q1 — Scope of "FAIL": verdict-only, or also wire a non-zero CLI exit?** Verdict-only
  is consistent with every existing fail-capable pack (mean_coverage etc.) and keeps this
  slice depth-first. Wiring `contig verify`/`run` to exit non-zero on a QC FAIL is a
  cross-cutting change affecting ALL fail packs, arguably a separate feature. Recommend
  **verdict-only** for this slice, flag the exit-code wiring as a deliberate follow-on.
- **Q2 — Exact FAIL bands.** Proposed, WES-safe, literature-grounded:
  ts_tv `fail_below 1.2 / fail_above 3.6`; het_hom `fail_below ~1.0 / fail_above ~3.0`;
  variant_count `fail_below 1` (essentially-empty call set) and **no** `fail_above` (a
  huge joint cohort is legitimately large — the absurd-count ceiling stays a soft WARN).
- **Q3 — Which checks this slice.** Brief says all three germline. Confirm variant_count
  gets only a `fail_below` (broken/truncated calling), not a `fail_above`.

## Guardrail check (CLAUDE.md)

On-thesis Layer-2 verification depth (make the verdict harder to fool). No Layer-1, no
clinical claim (engineering "broken call set" tripwire), no proprietary data (bands are
public literature). Test-first.
