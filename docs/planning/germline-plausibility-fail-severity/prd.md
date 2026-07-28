# PRD: germline-plausibility-fail-severity

Status: draft for review. Owner: aliz. Branch: `feat/germline-plausibility-fail-severity/aliz`.
Capability: **C3 follow-on** (biological-plausibility verification — first FAIL gate on the
germline axis). Sources: `docs/planning/_card/issue.md` (contig-next handoff),
`_card/understanding.md` (Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md` C3.

## Problem Statement

Contig's biological-plausibility axis is the part of the verdict that is supposed to catch
a run that **executed fine but produced biologically broken output** — the silent-failure
class generic QC misses. For germline variant calling it computes three metrics from the
VCF (`ts_tv`, `het_hom`, `variant_count`) and scores them against `VARIANT_RULE_PACK`
(`src/contig/verification/rule_pack.py:49-86`).

Today **all three are WARN-only** — they carry no `fail_below`/`fail_above`, so a call set
that is essentially noise (Ti/Tv ≈ 0.5, the signature of random/garbage calls) produces a
WARN, never a FAIL. A WARN does not move the verdict to FAIL and is easy to overlook. This
directly contradicts the moat mandate in `CLAUDE.md` #2 — **"make every verdict harder to
fool"** — and is inconsistent with the *did-it-run* QC packs (`mean_coverage fail_below:10`,
methylseq, ampliseq, mag, scrnaseq), which already FAIL on gross failure as honest
engineering defaults through the exact same scorer.

**Evidence it's real:** a Ti/Tv far from the expected ~2.0 (WGS) / ~3.0–3.3 (WES) is the
canonical "this call set is garbage" signal in germline QC; a near-empty call set means
calling truncated or failed. The germline pack originally carried `[1.5, 3.0]` FAIL bands;
they were **deliberately removed in v0.3.0** "until calibrated on real data"
(`CHANGELOG.md:1386-1388`). This slice reinstates FAIL severity with **wider, WES-safe,
gross-implausibility-only** bands so it can never false-FAIL a legitimate run.

This is Layer-2 verification depth (`CLAUDE.md`): it makes the existing verdict harder to
fool without new data, new tools, or any clinical claim.

## Goals & Success Metrics

- **G1 — Germline plausibility can FAIL a grossly-implausible run.** A germline VCF whose
  Ti/Tv, het/hom, or variant-count is grossly outside the plausible range yields a
  QCResult with `status="fail"`, which drives `record.verdict` → FAIL (surfaced in
  `render_run_report`, `contig show --explain`, provenance, and the dashboard).
  *Metric:* a test with a noise-level Ti/Tv (~0.5) produces `status="fail"` and
  `overall_verdict(...) == "fail"`.
- **G2 — Zero false FAILs on legitimate runs.** A legitimate WGS (Ti/Tv ~2.0, het/hom
  ~1.5) and a legitimate WES (Ti/Tv ~3.0–3.3) both stay PASS/WARN, never FAIL.
  *Metric:* boundary tests at 2.0, 3.3, and just-inside each `fail_*` bound assert
  `status != "fail"`.
- **G3 — Honest engineering framing, not a clinical claim.** The FAIL bands are documented
  as gross "broken call set" tripwires on the same tier as `mean_coverage fail_below`,
  never a biological/pathogenicity claim.
- **G4 — No regression, no scope creep.** Full suite stays green (baseline **1479 passed,
  1 skipped**, `uv run pytest`). Only germline `VARIANT_RULE_PACK` changes; somatic /
  RNA-seq / annotation / sex-check plausibility stay WARN-only.

## User Personas & Scenarios

- **A, lone computational biologist:** runs germline calling on a mis-prepared sample; the
  caller emits a noise-level call set that passes structural QC. Today: a WARN buried in
  the report. After: the verdict reads **FAIL** with the exact metric named
  ("ts_tv=0.5 — implausible for a real germline call set"), so they catch it before
  building on garbage.
- **C, core facility:** wants a consistent gate so a broken germline call set never ships a
  green-looking verdict to a non-expert PI. The FAIL verdict gives them that gate without
  claiming any diagnostic interpretation.

## Requirements

### Must-have (this slice)

- **R1 — `ts_tv_ratio` FAIL band.** Add `fail_below: 1.2`, `fail_above: 3.6` to the
  `ts_tv_ratio` rule in `VARIANT_RULE_PACK`, keeping the existing WARN band
  (`warn_below: 1.8`, `warn_above: 2.4`) intact. Rationale: legit WGS ~2.0 and WES ~3.0–3.3
  stay ≤ WARN; a random/noise call set (~0.5) FAILs.
- **R2 — `het_hom_ratio` FAIL band.** Add `fail_below: 1.0`, `fail_above: 3.0`, keeping the
  WARN band (`warn_below: 1.4`, `warn_above: 2.5`). Rationale: het/hom is more
  population/capture-sensitive than Ti/Tv, so the FAIL band is deliberately wider than the
  WARN band and only trips a grossly-off ratio.
- **R3 — `variant_count` FAIL floor only.** Add `fail_below: 1` (an essentially-empty call
  set = broken/truncated calling). **Do NOT add `fail_above`** — keep `warn_above:
  20_000_000` as the existing SOFT WARN ceiling; a large joint-called cohort is
  legitimately large and must never FAIL.
- **R4 — Scorer unchanged; data-only functional change.** `_status_for()`
  (`rule_pack.py:435-454`) already honors `fail_below`/`fail_above` via `.get()`;
  `evaluate()` and `evaluate_variant_plausibility()` pass status through with no clamp. No
  evaluator/reducer/CLI code changes — the change is the three rule dicts plus their
  comments.
- **R5 — Update the WARN-only assertions.** Update the tests and source comments/docstrings
  that assert germline plausibility is WARN-only (inventory in `_card/understanding.md`):
  `test_variant_metrics.py` (the "warns never fails" tests at ~242/306/319/334),
  `test_rule_pack.py:178`, and the comments at `rule_pack.py:44-72` /
  `variant_metrics.py:154,166`. This is a deliberate contract change, done test-first.
- **R6 — Tests-first, gross/boundary/legit fixtures.** New RED tests before the data
  change. Cover, per check: a grossly-out-of-band value → FAIL; a value just inside each
  `fail_*` bound → not FAIL (WARN or PASS); a legit WGS and WES value → PASS/WARN; the
  in-band PASS still holds; and the verdict-level reduction (a failing germline
  plausibility result drives `overall_verdict` → "fail").
- **R7 — Empty-call-set combined result is pinned.** An empty germline VCF yields
  `variant_count` **FAIL** (`fail_below: 1`) *and* `ts_tv`/`het_hom` **UNVERIFIED** (the
  ratios are uncomputable when there are no variants). FAIL dominates in `overall_verdict`,
  so the overall verdict is **FAIL**. A test asserts this exact combination so the
  FAIL-vs-UNVERIFIED interaction is unambiguous (and confirms the empty set is no longer a
  mere WARN — a strictly stronger, correct signal vs today).
- **R8 — Band-ordering invariant test.** For each germline rule, assert
  `fail_below ≤ warn_below ≤ warn_above ≤ fail_above` (over whichever bounds are present) —
  a cheap guard so a future mis-edit can never make FAIL land *inside* the WARN band
  (`_status_for` returns FAIL first, so incoherent bands would silently mis-score).

### Should-have

- **R9 — Docs synced.** A `CHANGELOG.md` entry under Unreleased; update
  `CAPABILITY_ROADMAP.md` C3 germline rows (`:432-452`, summary `:828`) and `FEATURES.md`
  from "WARN-capped / FAIL deferred" to "germline plausibility now FAILs on gross
  implausibility (WES-safe bands)". Keep the honesty caveat (engineering tripwire, not a
  clinical claim; somatic/RNA-seq/annotation still WARN-only).

### Out of scope (this slice)

- **CLI exit-code wiring.** Making `contig verify`/`contig run` exit non-zero on a
  QC-verdict FAIL is a cross-cutting change affecting **all** fail-capable packs
  (mean_coverage, methylseq, …), not just germline. Confirmed verdict-only for this slice;
  exit-code wiring is a deliberate, separately-scoped follow-on.
- FAIL severity for the somatic, RNA-seq, RNA-seq-composition, and annotation plausibility
  packs — they stay WARN-only.
- Capture-type-aware (WGS/WES/panel) bands. Contig does not persist capture type; the
  gross WES-safe band sidesteps this deliberately. Tighter per-capture bands are future
  calibration work.
- Sex-check plausibility (a separate bimodal axis, already its own constants).

## Technical Considerations

- **Chokepoint:** `src/contig/verification/rule_pack.py:54-78` (the three germline rule
  dicts). One data edit; the scorer, evaluator, reducer, report, provenance, and dashboard
  all consume it unchanged.
- **Verdict flow (verified in the dig):** `evaluate_variant_plausibility`
  (`variant_metrics.py:151-200`) → `rule_pack.evaluate` → `_status_for` →
  QCResult(status) → `runner.py:295` into `qc_results` → `overall_verdict`
  (`models.py:78-96`, `if "fail" in statuses: return "fail"`) → `record.verdict`. No
  `kind`-based severity cap anywhere.
- **UNVERIFIED path preserved:** `ts_tv`/`het_hom` still degrade to `unverified` when the
  ratio is uncomputable (`None`); `variant_count` is always an int, so a real 0 rides the
  band — and now `fail_below: 1` makes an empty call set an honest **FAIL**, not a WARN
  (a strictly stronger, correct signal; note this in the changelog).
- **Reproducibility/verification impact:** strengthens the verdict (a broken germline call
  set now fails the verdict rather than warning). No change to run artifacts, pins, or the
  reproduce bundle. Rule packs are versioned data pinned into the RunRecord, so the band
  change is auditable.
- **No raw-read egress, no network, no tool execution** — pure local scoring of an existing
  metric.

## Risks & Open Questions

- **R-risk-1 — False FAIL on an exotic-but-valid germline run.** Mitigated by the WES-safe
  wide bands (Ti/Tv [1.2, 3.6] clears WGS ~2.0 and WES ~3.3; het/hom [1.0, 3.0] clears
  typical ~1.5) and by scoping FAIL to *gross* implausibility only. Residual risk: an
  unusual-but-real cohort (e.g. a targeted panel with skewed Ti/Tv) — acceptable because
  the band is deliberately gross-only and the value is always named in the message.
- **R-risk-2 — Contract-reversal churn.** Reinstating a removed contract touches several
  tests/comments/docs. Mitigated by the Phase-2 inventory (exact file:line checklist) and
  by doing it test-first.
- **R-risk-3 — "Calibrated on real data" objection.** The bands are literature-grounded
  public knowledge (Ti/Tv ~2.0 WGS / ~3.0–3.3 WES; noise ~0.5), used as gross engineering
  tripwires, exactly as the did-it-run packs already do. Not presented as a calibrated
  clinical threshold.
- **Open:** none blocking — the three product decisions (verdict-only; WES-safe wide bands;
  variant_count fail_below only) are resolved.

### Challenge (due diligence)

- *"What if this launched and failed?"* The likely failure mode is a false FAIL on a
  legitimate run eroding trust in the verdict — which is why FAIL is scoped to gross-only,
  WES-safe bands, and why exit-code wiring (which would make a false FAIL block a run) is
  explicitly deferred.
- *"What are we NOT building by doing this?"* A broader calibration effort across all
  plausibility packs. Deliberately narrow: germline first, depth-first, as the proof that
  the plausibility axis can gain teeth honestly.

## Out of Scope (confirmed)

See "Out of scope (this slice)" above: CLI exit-code wiring; non-germline plausibility
FAIL bands; capture-type-aware bands; sex-check; any clinical/pathogenicity claim; any
Layer-1 workflow authoring.
