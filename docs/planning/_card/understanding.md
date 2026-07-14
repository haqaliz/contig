# Understanding — feat / somatic-strelka2-vaf (Phase 2 deep dig)

Grounded in a read-only code-map of the somatic verification path. All anchors are in
this worktree.

## What the work is really asking

Extend the somatic biological-plausibility verdict so a **VAF distribution check also
fires from the Strelka2 call set**, not just Mutect2. Today `somatic_plausibility.py`
derives `median_vaf` only from Mutect2 FORMAT `AF`/`AD`/`DP`; a Strelka2 VCF carries
neither, so its VAF signal is unused. This closes the roadmap's deferred item
"Strelka2-native VAF (tier-count derivation — non-Mutect2 VCFs degrade to UNVERIFIED)".

## Affected areas (what's reusable vs net-new)

**Reusable (do NOT rebuild):**
- **Strelka2 VCF locator** — `verification/somatic_concordance.py::select_caller_vcfs`
  (`:164-211`) matches a caller by lowercased path **component** (`strelka` / `mutect2`)
  below `run_dir` and returns the split `*.somatic_snvs*` / `*.somatic_indels*` pair. The
  somatic `_discover_qc` gate already computes these for concordance — reuse it, do not
  re-glob.
- **Emission pattern** — `somatic_plausibility.py::evaluate_somatic_plausibility`
  (`:224-281`): a `by_metric` dict → shared `evaluate(..., SOMATIC_PLAUSIBILITY_PACK)` →
  a `None`→`status="unverified"` loop (`:254-268`). Mirror this exactly so an
  absent/unparseable Strelka VAF becomes one honest UNVERIFIED, never a false pass.
- **Parser technique** — `somatic_plausibility.py::_vaf_from_sample`/`_read_somatic`
  (`:86-163`): the `{FORMAT_key: index}` → read `cols[8]`/`cols[tumor_idx]` streaming
  shape. The new tier-count parser mirrors this shape (different keys).
- **Band engine + pack** — `rule_pack.py::SOMATIC_PLAUSIBILITY_PACK` (`:296-314`, WARN-only,
  no `fail_*`) + `evaluate` (`:454-473`). A new WARN-capped rule rides it unchanged.
- **Gate** — `runner.py::_discover_qc` somatic block (`:333-367`), a dedicated (non-MultiQC)
  gate. Wiring 1 = Mutect2 VAF; wiring 2 = concordance. The Strelka VAF slots in as a
  parallel call in this same block.

**Net-new surface (this slice writes it):**
1. A **Strelka2 tier-count VAF parser** — SNV: tier1 of `{ALT}U` / (tier1 `{REF}U` + tier1
   `{ALT}U`) using the `AU/CU/GU/TU` per-base counts; indel: tier1 `TIR` / (tier1 `TAR` +
   tier1 `TIR`). Each field is a `(tier1,tier2)` pair; use tier1. Any missing/malformed/
   multiallelic/zero-denominator record → `None` (omit-never-guess), mirroring
   `_vaf_from_sample`.
2. A **Strelka2 tumor-column resolver** — Strelka2 writes fixed `NORMAL` then `TUMOR`
   sample columns and has **no** `##tumor_sample=` header, so resolve the tumor column by
   the literal `TUMOR` name in the `#CHROM` line (fall back to UNVERIFIED if absent — never
   guess positionally without the label).
3. The **first committed Strelka2 FORMAT fixture** — no repo fixture today has any
   `AU/CU/GU/TU`/`TAR/TIR` layout (grep = 0 hits); the concordance fixtures are FILTER-only
   8-column VCFs. Author a realistic `somatic_snvs` + `somatic_indels` fixture with
   `NORMAL`/`TUMOR` columns to pin the formula.

## Verdict-only (confirmed)

No persisted somatic/VAF model exists (`models.py` has `ReferenceIdentity`,
`AnnotationProvenance`, `SexInference` — none somatic). The somatic verdict is a
`list[QCResult]` (`kind="metric"`). **No model change, no provenance record, no reproduce
change.** Additive to the verdict only; gated to `somatic_variant_calling`.

## Key open decision (for the requirements interview)

**Corroboration metric vs Mutect2-absent fallback.** In a standard Contig somatic run BOTH
callers run (`--tools strelka,mutect2`), so Mutect2 VAF already fires. Two designs:
- **(A) Corroboration (recommended):** emit a **distinct** `strelka_median_vaf` metric
  alongside Mutect2's `median_vaf`, so both callers' VAF distributions are checked
  independently — verdict harder to fool, cross-caller signal, and it subsumes the fallback
  (Strelka fires whether or not Mutect2 is present). Matches the brief's "the VAF axis fires
  from the Strelka2 call set as well."
- **(B) Fallback only:** derive Strelka VAF **only when the Mutect2 VCF is absent**. Matches
  the literal roadmap phrasing but rarely fires (Mutect2 is normally present), so lower
  value.

Recommend (A). Settle in prd-interview; it drives the metric name, the pack rule, and the
gate wiring.

## Ambiguities / risks to resolve in the PRD

- **Tier-count VAF formula correctness** — the top correctness risk. Pin the SNV
  (`{ALT}U`/(`{REF}U`+`{ALT}U`), tier1) and indel (`TIR`/(`TAR`+`TIR`), tier1) formulas in
  the fixture; DP-based denominators are a documented alternative but the ref+alt tier1
  denominator is Strelka2's own AF definition. Honest fallback (UNVERIFIED) absorbs any
  parse failure.
- **SNV + indel split** — Strelka2 emits two files; decide whether to pool both files'
  per-record VAFs into one `median` (recommended — one distribution, matching how Mutect2's
  single VCF pools SNV+indel) or report separately. Recommend pooled, keyed off the
  concordance union pattern.
- **Band values** — reuse `median_vaf`'s existing `warn_below 0.05 / warn_above 0.95`
  (uncalibrated engineering default) for the Strelka metric; FAIL severity + real-cohort
  calibration stay deferred.
- **Multiallelic** — exclude (mirror `_biallelic`), since tier-count VAF is per-single-ALT.

## Guardrail check (CLAUDE.md)

Layer-2 verification depth (on-thesis). No Layer-1. No raw-read egress (reads a small VCF
on the user's compute). No new dependency (stdlib parser). Research-use only, WARN-capped,
never a clinical judgement. Test-first, no real sarek/samtools in CI.
