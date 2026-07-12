# PRD: germline-variant-count-plausibility

Status: draft for review. Owner: aliz. Branch: `feat/germline-variant-count-plausibility/aliz`.
Capability: **C3 biological-plausibility verification** — the last unbuilt item on the germline
build list (`docs/technical/CAPABILITY_ROADMAP.md` C3, "expected variant-count band for the
assay", ~line 421). Sources: `docs/planning/_card/issue.md` (contig-next handoff, 2026-07-12),
`docs/planning/_card/understanding.md` (Phase-2 dig).

## Problem Statement

A germline (`variant_calling`) run can complete "successfully" — every process exits 0, the
output VCF exists and is non-empty as a file, structural QC passes — yet produce a
**biologically meaningless call set**: near-zero variants (a silently failed calling step, a
truncated/empty VCF, the wrong file located) or an absurdly inflated count. Today the germline
verdict has three biological axes (Ti/Tv, het/hom, karyotypic sex-check) but **no sanity check on
the sheer number of variants called**, so this gross-failure class passes the verdict unflagged.

This is squarely the moat (`CLAUDE.md`): "make every verdict harder to fool." The somatic assay
already ships the symmetric check (`somatic_variant_count`, `SOMATIC_PLAUSIBILITY_PACK`); germline
is the gap. No incumbent (Galaxy, Terra, Seqera, DNAnexus) issues any output-correctness verdict,
let alone a variant-count sanity signal (`FEATURES.md:61-68`).

**Evidence it's real:** a near-empty germline VCF from a partial/failed calling run is a classic
"completed but wrong" outcome; the C3 germline build list explicitly names an expected
variant-count band as a wanted check (`CAPABILITY_ROADMAP.md:~421`), and it is the only germline
item on that list not yet shipped (v0.3.0 landed Ti/Tv + het/hom; the sex-check slice landed the
karyotypic check).

## Goals & Success Metrics

- **G1 — Catch a grossly-off germline variant count.** A completed `variant_calling` run whose
  primary VCF has a variant count outside a wide band emits one WARN-capped
  `variant_count:<sample>` QC result naming the measured count and expected band, contributing to
  the verdict (at most WARN). *Metric:* a test with an out-of-band fixture (e.g. 2 variants) yields
  a `warn` `variant_count` result; never `fail`.
- **G2 — Zero false failures, verdict-safe.** The check is WARN-capped: it never FAILs, never
  changes the `contig run`/`verify` exit code, and a normal-count run reads PASS. *Metric:* an
  in-band fixture yields `pass`; an out-of-band fixture never yields `fail` and never flips the exit
  code.
- **G3 — Never a false pass on absent input.** No primary VCF located → the check is not emitted
  (silent skip; structural QC owns a genuinely-missing output), never a fabricated PASS.
  *Metric:* a run dir with no `*.vcf.gz` produces no `variant_count` result.
- **G4 — No regression, additive only.** Full suite stays green (baseline **1479 passed, 1
  skipped**). No new `FailureClass`, model, persisted-record, dependency, or exit-code change; no
  gate edit (the check rides the existing germline plausibility gate).

## User Personas & Scenarios

- **A, lone computational biologist:** runs germline calling on a cohort; a mis-located or
  truncated VCF yields ~0 variants; today the verdict is silent, tomorrow it WARNs "variant count 2
  is far below the expected band" so the run is caught before the result is trusted.
- **C, core facility:** runs many germline samples for non-expert PIs; wants a consistent
  guard so a catastrophically empty (or absurd) call set never silently ships as a clean verdict.

## Requirements

### Must-have (this slice)

- **R1 — `variant_count` metric.** Add `variant_count: int` to `VariantMetrics`
  (`verification/variant_metrics.py`), computed as `len(sites)` from the `parse_vcf(vcf_path)`
  result the function **already computes** (`variant_metrics.py:114`) — no second parse, no new
  reader/module. Definition (documented in the code and the message): **the number of distinct
  variant sites `(CHROM, POS, REF, ALT)` in the primary sample** — multiallelic records counted
  once, not PASS-filtered (consistent with how `parse_vcf` and the somatic count both ignore
  FILTER). *(Confirmed decision: Design A — distinct sites via the existing parse.)*
- **R2 — WARN-only wide band rule.** Add a `variant_count` rule to the **registered**
  `VARIANT_RULE_PACK` (`rule_pack.py:49-75`), carrying only `warn_below: 10` and
  `warn_above: 20_000_000` (no `fail_*`), with a clear `message`. The band is a deliberately loose,
  **uncalibrated** gross-failure catch that passes WGS (~4–5M), WES (~20–50k), and targeted panels
  (~hundreds) alike. The `warn_above` is a **soft "absurd-count" tripwire, not a calibrated
  ceiling** — a code comment must say so, so a future reader does not mistake it for a validated
  bound (a very large joint-called cohort tripping it is an honest "unusually large, check it" WARN,
  never a block). *(Confirmed decisions: one wide catch-gross-only band; keep both bounds.)*
- **R3 — Select the rule in the germline plausibility path.** Extend
  `evaluate_variant_plausibility` (`variant_metrics.py`) to select and evaluate the new
  `variant_count` rule via the existing `_rule_by_check` idiom (`variant_metrics.py:129-134`,
  which today selects `ts_tv_ratio`/`het_hom_ratio`). No change to `runner._discover_qc` — the
  check rides the existing `evaluate_variant_plausibility(vcfs[0])` call at `runner.py:291`.
- **R4 — Honest contract, identical to every C3 sibling.** At most WARN, never FAIL, never changes
  the exit code. `variant_count` is always an int when the VCF parses, so a genuinely-empty or
  unparseable VCF → count 0 → **WARN below band** (honest, never a false pass); no VCF at all → the
  gate never fires (silent skip). No special UNVERIFIED-on-zero case for slice 1 (mirrors somatic).
- **R5 — Verdict-only, no provenance.** No `RunRecord` provenance record (symmetric to
  `somatic_variant_count`, which is verdict-only; unlike the sex-check's `SexInference`). No model
  change beyond the `VariantMetrics` dataclass field.
- **R6 — Tests-first, real inline fixtures.** Strict TDD, mirroring
  `tests/verification/test_variant_metrics.py` (inline VCF strings → `tmp_path`, helpers
  `_HEADER`/`_vcf_line`/`_write_vcf`). Cover, each as its own test:
  - in-band count → `pass`;
  - out-of-band-low count → `warn`, never `fail`;
  - **count 0 (empty/only-header VCF) → `warn` below band, NOT `unverified`** (pins R4: the shared
    `evaluate_variant_plausibility` path must not route a real 0-count into the ts_tv/het_hom
    UNVERIFIED branch);
  - out-of-band-high count → `warn` (asserts the `warn_above` tripwire fires);
  - the emitted result's **`check` key is `variant_count:<sample>`** and it groups with the other
    germline plausibility rows (not a stray ungrouped row);
  - gzip input parses;
  - multi-sample VCF → counts the primary sample's distinct sites;
  - `VariantMetrics.variant_count` holds the expected int.

  No mocks, no network, **no real nf-core/sarek run**.

### Should-have

- The `message` states the definition ("distinct germline variant sites, primary sample") so a
  WARN is self-explanatory and the dedup/multiallelic semantics are not surprising.

### Nice-to-have (explicitly later, not now)

- FAIL severity once the band is calibrated on real human germline data.
- Capture-aware bands (WGS/WES/panel) — needs a capture signal Contig does not reliably have today.
- Per-sample counts for multi-sample germline VCFs (today: primary sample only, consistent with
  `variant_metrics`/`sex_plausibility`).
- A dashboard card / "expected variant-count" surface treatment beyond the existing QC panel row.
- Folding the count distribution into the C6 eval corpus.

## Technical Considerations

- **Architecture fit:** pure Layer-2 verification. Reuses the germline VCF reader
  (`concordance.parse_vcf`), the registered-rule-pack + `_rule_by_check` selection idiom, and the
  existing `_discover_qc` germline gate. This is the germline-native pattern (how ts_tv/het_hom
  already work), **not** a mechanical copy of the somatic module (Design B, rejected: a second
  parse + a new module/gate for no benefit).
- **Verification/reproducibility impact:** additive to the verdict; deterministic; no persisted-
  record or bundle-schema change, so reproduce is unaffected. Captures a new per-assay count signal
  into the run's QC results (moat #2 corpus fuel).
- **No raw-read egress:** reads a VCF already on the user's compute; only a scalar count and a
  status ever surface.
- **Gets better with better models:** the band is a scoped sanity signal now; as calibration data
  accrues, the same axis tightens and can gain FAIL severity — the orchestrator improves, never
  redundant.

## Risks & Open Questions

- **R-risk-1 (primary product risk): false WARNs from a mis-set band.** Mitigated by the
  deliberately wide, WARN-only band (never FAIL, never blocks) and the honest message. Calibration
  deferred by design.
- **R-risk-2: `len(parse_vcf())` dedup/multiallelic semantics differ slightly from a raw record
  count.** Accepted and documented (negligible for a wide band); the metric is defined honestly as
  "distinct variant sites," not "records."
- **R-risk-3: `warn_above: 20M` could WARN on a legitimately huge WGS joint-called cohort.**
  Accepted (decision: keep both bounds). It is a soft tripwire, WARN-only, never blocks; a large
  cohort tripping it is an honest "unusually large, check it" signal, and the code comment marks it
  as uncalibrated. Revisit with real data if it proves noisy.
- **Open:** exact `message` wording — trivial, settle in implementation; the band values are
  uncalibrated placeholders by design.

## Out of Scope

- FAIL severity and any real-data band calibration.
- Capture-type (WGS/WES/panel) detection or capture-aware banding.
- Per-sample multi-sample counts.
- Any new provenance record, persisted-record, `FailureClass`, or model beyond the
  `VariantMetrics.variant_count` field.
- Somatic changes (already shipped) and any dashboard work beyond the existing QC panel row.
- A real nf-core/sarek run in CI.

## Guardrail check (CLAUDE.md) — clean

Layer-2 verify-only (no Layer-1 workflow authoring); no raw-read egress; no correctness
over-claiming (WARN-capped, UNVERIFIED/skip never rendered as PASS, research-use sanity signal
never a clinical judgement); test-first with synthetic fixtures.
