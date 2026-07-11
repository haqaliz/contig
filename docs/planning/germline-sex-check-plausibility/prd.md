# PRD: germline-sex-check-plausibility

Status: draft for review. Owner: aliz. Branch: `feat/germline-sex-check-plausibility/aliz`.
Capability: **C3 biological-plausibility verification** (germline slice — the "sex-check"
item named at `docs/technical/CAPABILITY_ROADMAP.md:378`, deferred at `:347`).
Sources: `docs/planning/_card/issue.md` (contig-next handoff), `_card/understanding.md`
(Phase-2 dig), `CAPABILITY_ROADMAP.md` C3.

## Problem Statement

A germline variant-calling run can complete cleanly, pass structural and generic QC,
and still be a **sample mix-up, contamination event, or gross aneuploidy** that no
current check catches. A researcher's most common, most embarrassing failure — analysing
the wrong person's sample, or a swapped tumor/normal — leaves a fingerprint in the call
set itself: the sex chromosomes. A karyotypic-male (XY) sample shows near-zero
heterozygosity on the non-PAR X and carries Y-chromosome variants; a karyotypic-female
(XX) sample shows autosomal-level X heterozygosity and no real Y variants. When those two
independent signals **disagree**, something is wrong with the sample or the pipeline.

Contig computes `ts_tv` and `het_hom` from the VCF already (`variant_metrics.py`) but has
no sex-consistency check. This is squarely the moat (`CLAUDE.md`: "make every verdict
harder to fool") and a named-but-unbuilt C3 slice. No incumbent (Galaxy, Terra, Seqera,
DNAnexus) issues a sex-consistency verdict.

**Evidence it's real.** Sex-check concordance is a standard bioinformatics QC step
(e.g. `plink --check-sex`, peddy, somalier) precisely because sample swaps are common;
Contig is simply moving that well-established check inside the verified verdict, scoped
honestly to research use.

## Goals & Success Metrics

- **G1 — Fire a sex-consistency verdict on germline runs.** A `variant_calling` run with a
  VCF yields a `sex_plausibility` QCResult: PASS when the X-het and Y signals agree,
  **WARN** when they conflict or the X-het lands in the implausible mid-band.
- **G2 — Never a false pass; never a false alarm on normal runs.** Ambiguous/weak signal
  (too few X sites, no X contig) → **UNVERIFIED**, never PASS. A normal XX or XY run →
  PASS, not WARN (the bimodal-aware logic must not flag healthy females or males).
- **G3 — Deepen provenance.** The inferred karyotypic sex + its evidence is captured on the
  RunRecord and rendered in `contig methods` and the HTML report, and round-trips through
  the reproduce bundle.
- **G4 — Cannot regress the exit code.** WARN/UNVERIFIED `sex_plausibility` changes the
  printed verdict at most to `warn`; `contig run`/`verify` exit codes are unchanged
  (confirmed: exit is decided only by pipeline success / output drift, `cli.py:610-612`).

Measurable acceptance (test-first, no real nf-core run in CI):
- A male-pattern fixture (low X-het, Y variants) → PASS, message "consistent with XY".
- A female-pattern fixture (autosomal X-het, no Y) → PASS, "consistent with XX".
- A discordant fixture (autosomal X-het **and** Y variants) → WARN, never `fail`.
- A too-few-X-sites fixture → UNVERIFIED, `value is None`.
- A gzip round-trip yields identical results to the plain fixture.
- PAR sites are excluded from the X-het denominator on a build-detected fixture; a
  build-undetermined fixture falls back to unmasked with an honest note (still WARN-capped).

## User Personas & Scenarios

- **A — lone computational biologist:** runs germline calling on a cohort; a swapped
  sample is a silent, reputation-damaging error. The WARN + named reason ("X-het suggests
  XX but Y variants present") is the exact tripwire they want, with the raw `x_het_ratio`
  to judge it themselves.
- **C — core facility:** batch-processes many samples; a per-run sex-consistency line in
  the verified report + methods is an auditable QC gate a non-expert PI can trust.
- **D — biotech researcher:** wants the inferred sex in provenance/methods for defensible
  record-keeping.

## Requirements

### Must-have
- **M1 — X-heterozygosity ratio.** Over **biallelic** genotypes on the X contig
  (`chrX`/`X`, case-insensitive), excluding missing/hom-ref appropriately, compute the
  heterozygous fraction. Reuse `concordance.parse_vcf` (`{(CHROM,POS,REF,ALT): gt}`) — no
  new VCF reader, no new compute path.
- **M2 — PAR masking with build detection.** Exclude pseudoautosomal-region X sites (by
  POS) from the X-het denominator using standard GRCh37 and GRCh38 PAR coordinates. Detect
  the build from the VCF `##contig=<ID=chrX,length=…>` header (155,270,560 → GRCh37;
  156,040,895 → GRCh38). **Build undetermined → fall back to unmasked X-het**, recorded in
  the message/provenance as `par_masked=false, reference_build=null` (honest, still
  WARN-capped) — never guess a build.
- **M3 — Y-variant presence.** Count called variants on the Y contig (`chrY`/`Y`,
  case-insensitive; PAR-Y excluded for consistency). Presence above a small floor is a
  positive male signal; **absence is uninformative and never penalizes** (a Y-less
  reference and a female sample are indistinguishable from the VCF alone — the load-bearing
  honesty of this slice).
- **M4 — One derived `sex_plausibility` result + raw metric.** Combine M1–M3 into a single
  PASS/WARN/UNVERIFIED QCResult built in the wrapper (bimodal signal → cannot use a single
  `evaluate()` band):
  - **PASS** — signals concordant: (low X-het) or (low X-het + Y present) → "consistent
    with XY"; (autosomal X-het + Y absent) → "consistent with XX".
  - **WARN** — discordant (autosomal X-het + Y present), or X-het in the implausible
    mid-band. Message names the conflict and the possible causes (aneuploidy /
    contamination / sample swap). WARN-capped, **never FAIL**.
  - **UNVERIFIED** — fewer than the minimum biallelic X sites, or no X contig present.
  - Also emit an **informational** `x_het_ratio` QCResult (the raw number) so the
    researcher sees the underlying signal.
- **M5 — Wiring.** Add to `_discover_qc` germline block (`runner.py:254-264`), gated
  `assay == "variant_calling"`, reusing the same located `vcfs[0]`. WARN/UNVERIFIED cannot
  change the exit code.
- **M6 — Provenance capture + surfacing.** Capture a `SexInference` record onto
  `RunRecord` at `_finalize` (gated to `variant_calling`), render it in `contig methods`
  and the HTML provenance panel, and **round-trip it through the reproduce bundle** with
  pre-slice back-compat (legacy bundles default the field to `None`).
- **M7 — Thresholds single-sourced.** X-het low/high cutoffs, min-X-sites floor, and
  Y-present floor live as named constants (a `SEX_PLAUSIBILITY_PACK` or module constants in
  `rule_pack.py`), documented as **uncalibrated engineering defaults**. Not registered in
  `_RULE_PACKS` (follows `SOMATIC_PLAUSIBILITY_PACK`).

### Should-have
- **S1** — Surface the inferred sex on the Next.js dashboard provenance/QC card (reads the
  captured `SexInference`; no engine recompute).

### Nice-to-have
- **N1** — Y-PAR masking parity with X-PAR (small refinement of M3).

## Technical Considerations

- **Reuse, don't rebuild:** `parse_vcf` supplies CHROM+POS+GT; the module mirrors
  `variant_metrics.py`'s shape (compute fn → `evaluate_sex_plausibility` → hand-built
  UNVERIFIED branch). New file `verification/sex_plausibility.py`, test
  `tests/verification/test_sex_plausibility.py`.
- **Build detection needs the header**, which `parse_vcf` discards → the module also does a
  light `##contig` header scan (same gzip-transparent open). Keep the function pure: VCF
  path in → `(SexInference, list[QCResult])` out.
- **Provenance model:** a new `SexInference` pydantic model on `RunRecord`
  (`inferred_sex`, `x_het_ratio`, `x_sites`, `y_variant_count`, `par_masked`,
  `reference_build`), captured at `_finalize` like `AnnotationProvenance`/`ReferenceIdentity`
  (C5 pattern), gated to `variant_calling`. A `mode="before"`/default keeps pre-slice
  bundles loading.
- **First-sample limitation inherited** from `parse_vcf` (reads sample column 9 only).
  Multi-sample joint VCFs get the first sample's sex — documented, a deferred follow-on,
  consistent with `variant_metrics.py`.
- **No raw-read egress, Layer-2 only, no new dependency, no network.** Runs on the VCF
  already on the user's compute.

## Risks & Open Questions

- **R1 — False alarms train users to ignore it (the headline risk).** Mitigated by
  bimodal-aware logic (both extremes PASS), loose uncalibrated cutoffs, no-Y-penalty, and
  WARN-cap. FAIL severity + threshold calibration on real data are explicitly deferred.
- **R2 — PAR coordinates / build lengths must be exact.** Pinned as constants and asserted
  in tests against known values; a wrong constant is caught by the male-pattern fixture.
  Build-undetermined fall-back keeps a novel reference from producing a false alarm.
- **R3 — Non-human / non-standard karyotypes** (XXY, XYY, XO, non-human references) produce
  genuinely ambiguous signal → UNVERIFIED or WARN with a named reason, never a confident
  wrong PASS. This is a feature of the honest contract, not a bug.
- **OQ1 — Exact numeric cutoffs** (X-het low ≤ ~0.1, high ≥ ~0.2; min X sites ~20; Y floor
  ~5). Resolved as engineering defaults in the aspect spec; refined only against real data
  later.

## Out of Scope

- **Reported-vs-inferred concordance** and the sample-sheet sex column it needs (named
  follow-on).
- **Per-sample sex for multi-sample VCFs** (first-sample only, inherited).
- **FAIL severity** and empirical threshold calibration.
- **Non-human sex-determination systems.**
- **Clinical sex/karyotype determination** — this is a research-use sanity signal only,
  never a clinical verdict (`USE_CASE_UNIVERSE.md` bright line).

## Aspects (decomposition)

1. **inference-core** — `sex_plausibility.py`: X-het + PAR masking + build detection +
   Y-presence + derived `sex_plausibility`/`x_het_ratio` results; `SEX_PLAUSIBILITY_PACK`
   constants; full unit tests. The science and the verdict.
2. **verdict-wiring** — `_discover_qc` germline gate extension in `runner.py`; integration
   test through the run path; confirm exit-code invariance.
3. **provenance-surfacing** — `SexInference` on `RunRecord`, `_finalize` capture,
   `contig methods` + HTML panel rendering, reproduce round-trip + back-compat (+ S1
   dashboard as should-have).
