# PRD: Strelka2-native VAF plausibility (somatic verdict)

**Capability:** C4 (somatic assay) — biological-plausibility axis, cross-caller VAF.
**Slug:** `somatic-strelka2-vaf` · **Branch:** `feat/somatic-strelka2-vaf/aliz`
**Status:** scope confirmed (interview 2026-07-14). Corroboration design (distinct metric).
**Sources:** `docs/planning/_card/issue.md` (contig-next handoff), `_card/understanding.md`
(Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md` C4.

---

## Problem Statement

Contig's somatic verdict checks a **VAF (variant allele fraction) plausibility** band, but
derives it **only from the Mutect2 VCF** (`verification/somatic_plausibility.py` reads
FORMAT `AF`, else `AD_alt/DP`, tumor via `##tumor_sample=`). Every Contig somatic run
launches `nf-core/sarek` with `--tools strelka,mutect2`, so a **Strelka2** call set is
**always produced** and already located by the shipped C1 concordance seam — yet its VAF
signal is unused, because Strelka2 somatic VCFs carry **no `GT` and no `AF`** (VAF is
encoded in tier counts). So a Mutect2-specific VAF artifact (a systematic caller bias, a
mis-set `--f1r2`/filtering step) can pass the verdict uncorroborated, and a somatic run
configured with only Strelka2 gets no VAF check at all.

`CAPABILITY_ROADMAP.md` C4 names this exact gap as deferred: *"Strelka2-native VAF
(tier-count derivation — non-Mutect2 VCFs degrade to UNVERIFIED)."* This slice closes it by
deriving VAF natively from Strelka2's tier counts and emitting it as a **distinct,
independent corroborating metric** alongside the Mutect2 VAF.

**Why it's real (not assumed):** the Strelka2 VCF is confirmed present and located today
(the C1 somatic-concordance slice reads both callers' PASS sites from the same run;
`somatic_concordance.py::select_caller_vcfs`). The only missing piece is the tier-count
parse — a well-defined, deterministic derivation.

**Moat fit (`CLAUDE.md`):** verdict-hardening — "make every verdict harder to fool" and
"widen what we can verify" — on an assay `CLAUDE.md` says is being hardened to the RNA-seq
bar. A second, independent caller's VAF distribution is a real corroboration signal, and it
gets better as models get better at adjudicating *why* two callers' VAF distributions
diverge. Squarely Layer-2; no Layer-1.

## Goals & Success Metrics

- **G1 — Strelka2 VAF fires as its own metric.** A completed somatic run emits a
  WARN-capped `strelka_median_vaf:<sample>` QCResult derived from the Strelka2 call set,
  **independent of and alongside** the Mutect2 `median_vaf`. *Metric:* a test with a
  Strelka2 fixture whose tier-derived median VAF is in-band → PASS; out-of-band → WARN
  (never FAIL); Mutect2's own metric is unchanged in the same run.
- **G2 — Correct tier-count derivation.** SNV and indel VAFs are derived by Strelka2's own
  AF definition and the pooled median matches a hand-computed expected value on a committed
  fixture. *Metric:* a fixture with known tier counts asserts the exact `median_vaf` value.
- **G3 — UNVERIFIED-when-absent, never a false pass.** No Strelka2 VCF found, an
  unidentifiable `TUMOR` column, or zero derivable tier VAFs → one honest
  `strelka_median_vaf` UNVERIFIED; no VCF at all → silent skip. *Metric:* tests for each
  path assert `status="unverified"`, `value=None`, `kind="metric"` (or no emission for the
  no-VCF case).
- **G4 — Additive & exit-neutral.** Never changes the `contig run`/`verify` exit code; no
  new `FailureClass`, model, persisted record, dependency, or reproduce change. *Metric:*
  the full suite (baseline **1539 passed, 1 skipped**) stays green + the new tests; no other
  assay's verdict changes.

## User Personas & Scenarios

- **Lone computational biologist / core-facility bioinformatician** running tumor–normal
  somatic calling. They get a completed run with a Mutect2 VAF check today; with this slice
  they also get an **independent Strelka2 VAF check**, so a caller-specific VAF anomaly is
  surfaced by cross-caller corroboration rather than trusted blind. Research-use only — a
  sanity signal, never a clinical/pathogenicity judgement.

## Requirements

### Must-have

- **M1 — Strelka2 tier-count VAF parser** (new `verification/strelka_vaf.py` — recommended,
  for a clean seam and its own test module, mirroring the per-tool parser modules
  `ampliseq_metrics.py`/`mag_metrics.py`; the plan may instead extend
  `somatic_plausibility.py` if that proves lighter). Pure, stdlib-only,
  streaming, gzip-transparent (reuse `_open_text`). Derivation:
  - **SNV** (`*.somatic_snvs*`): tier1 counts from the per-base FORMAT fields
    `AU/CU/GU/TU`; `VAF = tier1[{ALT}U] / (tier1[{REF}U] + tier1[{ALT}U])`, guarding a
    zero denominator. Single-base REF/ALT only.
  - **Indel** (`*.somatic_indels*`): `VAF = tier1[TIR] / (tier1[TAR] + tier1[TIR])`,
    guarding a zero denominator.
  - Each field value is a comma pair `tier1,tier2`; use **tier1**. Multiallelic (comma in
    ALT) excluded (mirror `_biallelic`). Any missing/malformed/non-numeric field or
    zero denominator → that record contributes **no** VAF (omit-never-guess), mirroring
    `_vaf_from_sample`.
- **M2 — Strelka2 tumor-column resolver.** Strelka2 has **no** `##tumor_sample=` header and
  writes fixed `NORMAL` then `TUMOR` sample columns; resolve the tumor column by the literal
  `TUMOR` name in the `#CHROM` line. If the `TUMOR` column is absent → UNVERIFIED (never
  guess positionally).
- **M3 — Pooled median across SNV + indel.** Pool all derivable per-record VAFs from **both**
  Strelka2 files into one distribution and take the median (mirrors how Mutect2's single VCF
  pools SNV+indel). Empty pool → `None` → UNVERIFIED.
- **M4 — Distinct WARN-capped pack rule.** Add a `strelka_median_vaf` rule to
  `SOMATIC_PLAUSIBILITY_PACK` (`rule_pack.py`), reusing `median_vaf`'s band
  (`warn_below: 0.05`, `warn_above: 0.95`, **no `fail_*`**) as an uncalibrated engineering
  default. It rides the existing `evaluate()` band engine unchanged.
- **M5 — Evaluator + emission.** A `evaluate_strelka_vaf_plausibility(snv_vcf, indel_vcf,
  sample=None) -> list[QCResult]` mirroring `evaluate_somatic_plausibility`'s `by_metric` →
  `evaluate(...)` → `None`→UNVERIFIED loop, so an absent/uncomputable metric is one honest
  UNVERIFIED `QCResult(kind="metric")`, never a false pass. Sample label = the `TUMOR`
  column name (or `"sample"`).
- **M6 — Gate wiring.** In `runner.py::_discover_qc`, somatic block (`:333-367`), add a
  parallel call that selects the Strelka2 VCFs via the **reused**
  `somatic_concordance.select_caller_vcfs` (already computed there for concordance — do not
  re-glob) and extends `results` with the Strelka VAF verdict. Mutect2 wiring 1 and
  concordance wiring 2 are untouched. Gated to `assay == "somatic_variant_calling"`.
  **Non-unique layout:** if `select_caller_vcfs` cannot uniquely resolve the Strelka2 pair
  (multi-tumor-pair or mismatched layout — the same conditions it flags UNVERIFIED for
  concordance), the Strelka VAF metric is a single honest `strelka_median_vaf` UNVERIFIED,
  never an arbitrary pick — consistent with the concordance path.
- **M7 — First Strelka2 FORMAT fixture(s).** No repo fixture has any `AU/CU/GU/TU`/`TAR/TIR`
  layout today (grep = 0). Author realistic synthetic `somatic_snvs` + `somatic_indels`
  Strelka2 VCFs with `NORMAL`/`TUMOR` columns and known tier counts, so G2 asserts an exact
  median.
- **M8 — Tests (TDD, no real tool).** RED-first. Cover: (a) in-band pooled median → PASS with
  the exact value; (b) out-of-band → WARN, asserted `!= "fail"`; (c) no `TUMOR` column →
  UNVERIFIED; (d) empty/zero-denominator/malformed tier fields → UNVERIFIED; (e) no Strelka
  VCF located → silent skip while Mutect2 metric still emits; (f) gate-level test proving both
  Mutect2 `median_vaf` and `strelka_median_vaf` appear for a run with both callers. No real
  nf-core/sarek or samtools in CI.

### Should-have

- **S1 — SNV/indel provenance in the message.** The QCResult message names Strelka2 as the
  source caller (mirrors the concordance "which caller" messaging), so the verdict surface
  distinguishes it from the Mutect2 metric.

### Nice-to-have

- **N1 — Per-file counts in the detail** (how many SNV vs indel records contributed) for
  eval-corpus richness. Cut if it complicates the parser.

## Technical Considerations

- **Reuse, don't rebuild:** the Strelka2 **locator** (`select_caller_vcfs`, matches by
  `strelka` path component, returns the split pair) and the **emission pattern**
  (`by_metric` → `evaluate` → `None`→UNVERIFIED). Net-new is only the tier-count parser, the
  `TUMOR`-column resolver, and the fixtures.
- **Verdict-only:** no persisted model (confirmed — somatic verdict is `list[QCResult]`); no
  `FailureClass`, no reproduce/`launch.json` change, no new dependency (stdlib parser).
- **No raw-read egress:** reads a small VCF already on the user's compute.
- **Reproducibility:** none affected — this is a read-time verdict metric, deterministic.

## Data Model

None. Output is `QCResult(kind="metric", check="strelka_median_vaf:<sample>", …)` — the
existing verdict shape. No `models.py` change.

## Risks & Open Questions

- **R1 — Tier-count VAF formula correctness (top risk).** Strelka2's `{ALT}U`/(`{REF}U`+
  `{ALT}U`) tier1 SNV AF and `TIR`/(`TAR`+`TIR`) tier1 indel AF are its own documented
  definitions; a DP-based denominator is a plausible-but-wrong alternative. Mitigated by:
  pinning the formula in a committed fixture with hand-computed expected medians (G2), and
  the UNVERIFIED-on-unparseable fallback (G3) so a mis-parse never becomes a false pass.
- **R2 — `TUMOR`-column convention.** Assumes sarek/Strelka2's `NORMAL`/`TUMOR` labels.
  Mitigated: resolve by the literal `TUMOR` name (not position); UNVERIFIED if absent. Flag
  to re-confirm against a real sarek 3.5.1 Strelka2 header if one is ever captured.
- **R5 — Fixtures encode OUR assumption, not a real header (accepted, eyes-open).** The
  formula and column convention are validated only against synthetic fixtures we author, so
  a wrong understanding of Strelka2's layout would pass green. Accepted because: (a) the
  ref+alt tier1 SNV / `TIR`/(`TAR`+`TIR`) indel formulas are Strelka2's own documented AF
  definitions (cited in the fixture comments), (b) the UNVERIFIED-on-unparseable fallback
  means a mis-parse degrades honestly, never a false pass, and (c) this matches how the
  entire somatic suite is built (synthetic fixtures, no real sarek in CI). Revisit-if a real
  Strelka2 somatic VCF is ever captured — commit one line as a golden anchor.
- **R3 — Multiallelic / non-SNV REF-ALT.** Tier-count VAF is per-single-base ALT for SNVs;
  exclude multiallelic and multi-base "SNV" records (mirror `_biallelic`); indels use
  `TAR/TIR` regardless of allele length.
- **R4 — Band is uncalibrated.** Reusing `median_vaf`'s 0.05/0.95 WARN band is a deliberate
  engineering default; FAIL severity and real-cohort calibration are out of scope.

## Out of Scope (confirmed deferred)

- **FAIL severity + real-cohort band calibration** (both VAF metrics stay WARN-capped).
- **The cross-column swapped-pair smell test** — a sibling deferred C4 item, separate slice.
- **PON / germline-resource reference wiring** for a real Mutect2 somatic run.
- **Strelka2 QSS/QSI quality-score or somatic-count plausibility** beyond VAF.
- **A dashboard card / "corroborated by" surface** for the somatic VAF.
- **Any `FailureClass`, self-heal, or eval-corpus/heal-scenario** change.
- **Any Layer-1 (NL→workflow) surface.**
