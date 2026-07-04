# Understanding — feat/somatic-vaf-plausibility (deep dig)

Grounded in two read-only code-map agents (plausibility machinery; somatic wiring +
VCF parsing) over the worktree checkout, plus direct reads of `variant_metrics.py`,
`concordance.py`, and `rule_pack.py`. `path:line` cited inline. Runner lives at
`src/contig/runner.py` (NOT `verification/runner.py`).

## What the work is really asking

Somatic (tumor–normal) variant calling shipped in v0.13.0 with **structural-only**
verification (`CHANGELOG.md:44-47`). Per `USE_CASE_UNIVERSE.md:135-138`, "a passthrough
that issues no verdict is not a Contig assay" — so somatic is currently the
weakest-verified assay. This slice adds a **C3-style biological-plausibility verdict**
for somatic, mirroring the shipped germline Ti/Tv slice (`variant_metrics.py`, v0.3.0),
scoped to a **VAF-distribution sanity** check computed from the somatic VCF.

This is a **follow-on slice of shipped work** (not a new assay), squarely Layer-2
(verify), and captures new eval data (a somatic VAF-distribution reference), so it
deepens moat #1 (the verified verdict) and moat #2 (the corpus).

## The exact pattern to mirror (fully mapped)

The germline C3 slice is the template, and it is clean:

- **Compute module** `verification/variant_metrics.py`: a pure VCF→metrics function
  (`variant_metrics()`), then `evaluate_variant_plausibility(vcf_path)` that (1) funnels
  the **computable** metrics through the shared `evaluate({sample: computable}, rules)`
  and (2) hand-rolls an explicit `QCResult(status="unverified", value=None, kind="metric")`
  for any metric it could not compute (`variant_metrics.py:137-179`). The shared
  `evaluate()` **silently skips** absent metrics (`rule_pack.py:304-323`), so the
  unverified branch must be hand-rolled — this is the near-zero-false-pass guarantee.
- **Rule pack** `rule_pack.py`: a WARN-capped `list[dict]` (only `warn_below`/`warn_above`,
  **no `fail_*`** → `_status_for` can never return `"fail"`, `rule_pack.py:271-290`).
  Plausibility packs are imported directly by their evaluator; they are **NOT** in the
  `_RULE_PACKS` registry (`rule_pack.py:253-260`) — so somatic does **not** need a
  `_RULE_PACKS` entry (and `rule_pack_for("somatic_variant_calling")` legitimately keeps
  raising `ValueError`, which the runner already catches to skip metric QC,
  `runner.py:43-51`).
- **Runner gate** `runner.py:_discover_qc` (`runner.py:38-76`): a per-assay `if` block.
  Germline locates its VCF via `manifest_for("variant_calling").required[0]` (=`"*.vcf.gz"`),
  `rglob`s under the run dir, takes `vcfs[0]`, calls `evaluate_variant_plausibility`
  (`runner.py:64-68`). MultiQC-independent.

## Everything already in place for somatic (no new wiring needed there)

- **Canonical assay key** is `"somatic_variant_calling"` **everywhere** — registry
  (`registry.py:25`), manifests (`structural.py:258`), methods label (`methods.py:23`),
  and the persisted `resolved_assay` that reaches `_discover_qc` (`cli.py:413`,
  `runner.py:261/295`). At QC time the `assay` argument is exactly this literal.
- **Structural manifest already exists**: `structural.py:258-261`
  `ExpectedOutputs(required=["*.vcf.gz"], gzip=["*.vcf.gz"])`, so
  `manifest_for("somatic_variant_calling").required[0]` already resolves to `"*.vcf.gz"`.
  Somatic sarek VCFs land at `results/variant_calling/<caller>/<tumor>_vs_<normal>/*.vcf.gz`.
- **Insertion point** for the new gate: `runner.py:69`, immediately after the germline
  block (ends line 68) and before the rnaseq block — a `if assay == "somatic_variant_calling":`
  clause using the identical VCF-locator idiom.

## 🔴 The real feasibility risk: VAF is not in the existing VCF parser

`concordance.parse_vcf` (`concordance.py:87-110`) and its `_genotype_from_columns`
(`concordance.py:113-130`) extract **only the `GT` subfield of the first sample column
(col 9)**. VAF needs a different FORMAT subfield, and somatic VCFs have **two** sample
columns. So there is **no reusable AF/AD/DP extractor** — new parsing is required. Three
coupled design decisions fall out, and they are the substance of this slice:

### Decision 1 — VAF source field (which caller, which FORMAT key)
- **Mutect2** emits `AF` directly in FORMAT (per-allele allele fraction) → the clean path.
  `AD`+`DP` (allelic depths / depth) is a deterministic fallback (`VAF = AD_alt / DP`).
- **Strelka2** does **not** emit `AF`; VAF must be derived from tier counts (`AU/CU/GU/TU`
  for SNVs, `TAR/TIR` for indels) — materially more complex.
- **Recommendation:** scope this slice to Mutect2 `AF` (optionally the `AD`/`DP` fallback),
  and **degrade to UNVERIFIED** (never a fabricated VAF) when the `AF` field is absent —
  which cleanly covers Strelka2 and any non-Mutect2 VCF. Strelka2-native VAF deferred.
  (The registry launches sarek with `--tools strelka,mutect2`, so a real run produces a
  Mutect2 VCF to read; the manifest globs `*.vcf.gz`, so the module must pick/So the
  locator or the evaluator must prefer the Mutect2 VCF — see Decision 3.)

### Decision 2 — tumor-sample-column selection (the meatiest)
A somatic VCF carries a **tumor** and a **normal** sample column; VAF sanity is about the
**tumor**. Mutect2 writes a `##tumor_sample=<name>` header line; the honest approach is to
read that header and map the name to its `#CHROM`-line column index. **Degrade to
UNVERIFIED** if the tumor sample cannot be identified (no header, unexpected shape) — never
guess a column. `_genotype_from_columns` is hardcoded to col 9, so this is genuinely new.

### Decision 3 — which VCF, and which metric(s)
- The glob `*.vcf.gz` matches multiple callers' outputs (strelka + mutect2, plus possibly
  filtered/unfiltered). The evaluator (or locator) must select the **Mutect2** VCF (the one
  with `AF`), and skip → UNVERIFIED if none is found. Selecting by path (`.../mutect2/...`)
  or by presence of `##tumor_sample=`/`AF` is the choice to make.
- **Metric(s)** — VAF-distribution sanity, WARN-capped, uncalibrated engineering defaults:
  - `median_vaf` within a plausible band (a tumor call set clustered near VAF≈1.0 or
    exactly 0.5 smells like germline leakage / a mis-paired normal; a plausible somatic
    set spans low subclonal to ~0.5 clonal-het).
  - Optionally `somatic_variant_count` band (too few / implausibly many calls).
  - Keep to **1–2 honest metrics**; more is false precision given no calibration.

## Ambiguities / open questions for the PRD interview

1. **Metric set:** `median_vaf` only, or also a `somatic_variant_count` band? (Recommend
   `median_vaf` as the flagship; count band only if it earns its keep.)
2. **VAF derivation:** Mutect2 `AF` only, or add the `AD`/`DP` fallback in slice 1?
3. **Multi-caller VCF selection:** prefer the Mutect2 VCF by path, by `AF`-presence, or by
   `##tumor_sample=` header? What if both strelka and mutect2 VCFs match the glob?
4. **Panel-of-normals presence check** (mentioned in the handoff "only if it falls out
   cheaply"): PON is not in the VCF FORMAT — it would be a header/structural check. **Lean
   defer** to a later slice unless trivially cheap; confirm.
5. **FAIL severity:** confirm WARN-cap only for this slice (bands uncalibrated), FAIL
   deferred — matching every prior C3 slice.

## Guardrail check (CLAUDE.md) — clean

Layer-2 only (we read the somatic VCF that sarek produced; we never author the pipeline);
no raw-read egress (deterministic, synthetic VCF fixtures, no real nf-core/sarek run in CI);
**no clinical over-claiming** — a somatic verdict is "ran correctly and reproducibly,"
research use, never a cancer diagnosis (`USE_CASE_UNIVERSE.md` bright line, `methods.py:23`
label); test-first (mirror `tests/verification/test_variant_metrics.py` synthetic-VCF style +
`test_run_qc.py` gating tests).

## Files this slice will touch

- **New** `src/contig/verification/somatic_plausibility.py` — tumor-aware VAF parse +
  `evaluate_somatic_plausibility(vcf_path) -> list[QCResult]`.
- **Edit** `src/contig/verification/rule_pack.py` — add `SOMATIC_PLAUSIBILITY_PACK`
  (WARN-capped) near `RNASEQ_PLAUSIBILITY_PACK:237-250`. No `_RULE_PACKS` change.
- **Edit** `src/contig/runner.py:69` — add the `somatic_variant_calling` plausibility gate.
- **New** `tests/verification/test_somatic_plausibility.py` — synthetic somatic-VCF unit
  tests (mirror `test_variant_metrics.py`).
- **Edit** `tests/verification/test_run_qc.py` — positive + negative gating tests (mirror
  `test_run_qc.py:262-303`).
- Possibly **Edit** `runner.py:40` docstring ("germline only" → include somatic).
