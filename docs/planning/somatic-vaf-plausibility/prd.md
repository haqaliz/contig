# PRD — Somatic VAF-distribution biological-plausibility verification

**Slug:** `somatic-vaf-plausibility` · **Type:** feat · **Owner:** aliz
**Capability:** C4 follow-on (biological plausibility for the somatic assay), a C3-style
slice on the assay shipped in v0.13.0.
**Status:** drafted for review (Phase 4 self-critique below).

---

## Problem Statement

Somatic (tumor–normal) variant calling shipped in v0.13.0 with **structural-only**
verification: the verdict confirms the sarek somatic run produced intact `*.vcf.gz`
outputs, but says nothing about whether the *result is biologically plausible*. The
CHANGELOG is explicit that this is "honestly structural-only … no somatic rule pack or
plausibility yet" (`CHANGELOG.md:44-47`). Per the standing discipline
(`USE_CASE_UNIVERSE.md:135-138`), "a passthrough that issues no verdict is not a Contig
assay" — so somatic is currently the **weakest-verified assay on the engine**.

The concrete silent-failure this closes: a somatic run that completed and produced a
well-formed VCF, but whose tumor variant allele-fractions are implausible — e.g. every
call at VAF≈1.0 or tightly at 0.5 (germline leakage / a mis-paired or swapped normal), or
a call set with no panel-of-normals filtering — passes structural QC today with a clean
verdict. That is exactly the "ran, but wrong" class the verify layer exists to catch.

**For whom:** the Contig ICP running cancer *research* pipelines — the lone computational
biologist and the core facility who need "did this somatic run actually produce a
sensible call set?" answered without hand-inspecting the VCF. Research use only; never a
cancer diagnosis (`USE_CASE_UNIVERSE.md` bright line).

**Evidence it's real:** this is the pre-designated next depth slice for C4
(`CAPABILITY_ROADMAP.md:280, 296-300` — "VAF distribution sanity, panel-of-normals
filtering present"), and it mirrors the already-shipped germline (v0.3.0) and RNA-seq
(v0.6.0) plausibility slices that established the pattern.

## Goals & Success Metrics

**Goal:** the somatic verdict gains a biological axis — a VAF-distribution sanity check
plus a variant-count band plus a panel-of-normals presence check — computed
deterministically from the run's own Mutect2 somatic VCF, WARN-capped and honestly
degrading to UNVERIFIED when it cannot compute.

**Success (all test-verifiable, no real nf-core run):**
- A synthetic Mutect2 tumor–normal VCF with plausible tumor VAFs → the somatic
  plausibility checks **PASS**, with `median_vaf` and `somatic_variant_count` values
  reported.
- A synthetic VCF with implausible tumor VAFs (e.g. all ≈1.0) → **WARN**, naming the
  metric and its band; **never FAIL** (WARN-cap).
- A VCF from which VAF cannot be derived (no `AF`, no usable `AD`/`DP`), or where the
  tumor sample cannot be identified → **UNVERIFIED** (`value=None`), **never a false pass**.
- A Mutect2 VCF whose header shows a PON was applied → PON check **PASS**; one that shows
  none → **WARN**; a VCF with no Mutect2 command header → PON check **UNVERIFIED**.
- The checks fire in `_discover_qc` **only** for `assay == "somatic_variant_calling"`
  (positive + negative gating test), reusing the existing structural-manifest VCF locator.
- `uv run pytest` green; the shipped-corpus detector guard and all existing suites
  unaffected (this slice adds verification only — no detector/`FailureClass` change).

**Non-metric guardrail (the trust bar):** zero false PASS. Every uncomputable path yields
UNVERIFIED, mirroring `evaluate_variant_plausibility` (`variant_metrics.py:167-178`).

## User Personas & Scenarios

- **A, lone computational biologist** runs a tumor–normal pair through Contig's somatic
  assay. Today she gets "outputs present." After this: "tumor VAF distribution is
  plausible (median 0.31), 4,812 somatic calls, panel-of-normals applied — corroborated,
  research use." If the normal was swapped, the median-VAF WARN flags it before she builds
  on a bad call set.
- **C, core facility** runs many somatic pairs; the VAF/count/PON checks give a
  consistent, auditable plausibility line per run that a non-expert PI can read, without a
  bioinformatician eyeballing every VCF.

## Requirements

### Must-have
1. **VAF derivation from the tumor sample of the Mutect2 somatic VCF.**
   - Read the tumor sample column, identified via the `##tumor_sample=<name>` header mapped
     to the `#CHROM` column index. If the tumor sample cannot be identified → contributes
     no VAFs (→ UNVERIFIED downstream). Never guess a column.
   - Per-record tumor VAF = FORMAT `AF` (Mutect2 allele fraction) when present; **else**
     `AD_alt / DP` from allelic depths (`AD` second value / `DP`); **else** the record
     contributes no VAF. Guard divide-by-zero (`DP==0`) and malformed `AD`.
   - **Multiallelic handling (default, tech-plan may refine):** VAF is computed on
     **biallelic records only** — a record with a comma in ALT (or a comma-listed `AF`/
     multi-value `AD` beyond ref+one-alt) is **excluded** from the VAF list, mirroring
     germline `_is_biallelic_snv` (`variant_metrics.py:50-56`). Unlike germline ts_tv,
     **indels are included** (VAF is an allele-fraction, not an SNV-only metric).
     `somatic_variant_count` counts these considered (biallelic) records.
2. **`median_vaf` metric** over all records that yielded a VAF; `None` when none did.
   Median is the standard statistical median — **for an even count, the mean of the two
   central values** (use stdlib `statistics.median`, deterministic, no new dependency).
   Cover an even-count fixture.
3. **`somatic_variant_count` metric** = number of variant records considered in the
   selected VCF (see the multiallelic decision in Must-have #1).
4. **`SOMATIC_PLAUSIBILITY_PACK`** (WARN-capped `list[dict]`, only `warn_below`/`warn_above`,
   no `fail_*`) in `rule_pack.py`, near `RNASEQ_PLAUSIBILITY_PACK`. Not registered in
   `_RULE_PACKS`. Bands are documented **uncalibrated engineering defaults**.
5. **Panel-of-normals presence check**: the decision keys off the **GATK command header**,
   not the path-based caller guess. Scan the selected VCF header for a GATK command line
   (e.g. `##GATKCommandLine`) and a `--panel-of-normals` / `--pon` argument. Command
   header **and** PON argument present → PASS; command header present **without** a PON
   argument → WARN; **no recognizable GATK command header** (a stripped/re-headed VCF, or a
   non-Mutect2 file that slipped the path filter) → UNVERIFIED (cannot tell — never a false
   pass). This makes the three-state test matrix unambiguous.
6. **`evaluate_somatic_plausibility(vcf_path) -> list[QCResult]`** in a new
   `verification/somatic_plausibility.py`: funnel computable metrics through the shared
   `evaluate({sample: computable}, rules)` and hand-roll the `status="unverified",
   value=None, kind="metric"` branch for each uncomputable metric (mirror
   `variant_metrics.py:137-179`). The PON check emits its own `QCResult`.
7. **Runner gate**: in `_discover_qc` (`runner.py`), add
   `if assay == "somatic_variant_calling":` immediately after the germline block
   (`runner.py:68`). Locate the VCF via `manifest_for("somatic_variant_calling").required[0]`
   (=`"*.vcf.gz"`), rglob under the run dir, **select the candidate whose path contains
   `mutect2`**; if none, the checks emit UNVERIFIED (or are skipped honestly — see Open
   Questions Q1). MultiQC-independent, like germline.
8. **Test-first**, synthetic somatic-VCF fixtures only (no real sarek/GATK run in CI):
   a unit test file mirroring `test_variant_metrics.py`, plus positive+negative gating
   tests in `test_run_qc.py` mirroring `:262-303`.

### Should-have
- Update the `_discover_qc` docstring (`runner.py:40`) so "(germline only) VCF
  plausibility" also names somatic.
- A CHANGELOG entry under `[Unreleased]` describing the slice, its WARN-cap, its
  UNVERIFIED-when-absent guarantee, and the deferrals.

### Nice-to-have (explicitly not required)
- Surfacing a "VAF distribution" summary line in the HTML report / dashboard (the
  QCResult already flows to both surfaces via the existing verdict plumbing; no bespoke
  UI in this slice).

## Technical Considerations

- **Pattern is proven and small.** Germline C3 (`variant_metrics.py`) is the direct
  template: pure VCF→metrics, WARN-capped pack, hand-rolled UNVERIFIED branch, one runner
  gate. Everything somatic-side is already wired: canonical key `somatic_variant_calling`
  is consistent across registry/manifest/methods/persisted `resolved_assay`
  (`cli.py:413`, `runner.py:261/295`), and `manifest_for("somatic_variant_calling")`
  already yields the `*.vcf.gz` locator (`structural.py:258-261`).
- **The one genuinely new primitive: a tumor-aware FORMAT-subfield reader.** The existing
  `parse_vcf`/`_genotype_from_columns` (`concordance.py:87-130`) extract **only** `GT`
  from the **first** sample column. This slice needs (a) a header parse to find the tumor
  column, and (b) a generic FORMAT-subfield read for `AF`/`AD`/`DP`. **Do not mutate the
  concordance GT reader** (it is load-bearing for C1); add the new parsing inside
  `somatic_plausibility.py` (a small, self-contained VCF pass). This keeps blast radius to
  the new module + the pack + one runner gate.
- **Verification/reproducibility impact:** additive to the verdict only. No exit-code
  change beyond what a WARN already does; no new persisted-record field; deterministic and
  reproducible (pure function of the VCF bytes). No raw-read egress — operates on the
  VCF on the user's compute.
- **Where it sits in the pipeline:** verify stage, `_discover_qc`, alongside the germline
  and rnaseq plausibility gates. No planner/runner/self-heal changes.
- **Guardrails (CLAUDE.md):** Layer-2 only (reads sarek's output; authors nothing); no
  clinical over-claiming (a somatic verdict is "ran correctly and reproducibly," research
  use — `methods.py:23` label); test-first.

## Data Model / Contracts

- No new persisted models. Output is `list[QCResult]` (existing model, `models.py:67-75`)
  with `kind="metric"` for the VAF/count checks. The PON check is also a `QCResult`;
  `kind="metric"` unless a more fitting existing kind applies (`kind` ∈
  `metric|structural|concordance`, `models.py:64`) — **decide in tech-plan**, defaulting
  to `metric` for consistency with the other plausibility checks.
- Check naming follows the shared convention `"<check>:<sample>"` for metric checks
  (`rule_pack.py:315`); the tumor sample name (from the header) is the natural sample label.

## Risks & Open Questions

- **R1 — Uncalibrated bands (false precision).** `median_vaf` and `somatic_variant_count`
  bands are engineering defaults, not validated on real cohorts. *Mitigation:* WARN-cap
  only (no FAIL), explicit "uncalibrated" docstrings, UNVERIFIED-when-uncomputable —
  identical posture to every prior C3 slice. FAIL severity deferred until calibrated.
- **R2 — Tumor-column identification is convention-dependent.** Relies on Mutect2's
  `##tumor_sample=` header. *Mitigation:* degrade to UNVERIFIED (never guess) when the
  header is missing/unexpected; cover the missing-header case with a test.
- **R3 — `somatic_variant_count` band is assay/target-dependent** (WES vs WGS vs panel
  differ by orders of magnitude), so a single band is coarse. *Mitigation:* very wide
  WARN band tuned only to catch gross failure (near-zero or absurdly many calls); document
  as coarse; revisit when target-type is known to the engine.
- **Q1 (for tech-plan):** when no `mutect2`-path VCF is found under the run dir, should the
  somatic gate **skip silently** (like germline when `vcfs` is empty, `runner.py:66-68`)
  or **emit an explicit UNVERIFIED**? Lean: skip silently if *no* VCF at all (structural QC
  already covers "missing output"), but emit UNVERIFIED if VCFs exist but none is Mutect2
  (we had something to check and honestly could not). Resolve in the plan.
- **Q2 (resolved; default set in Must-have #1):** multiallelic `AF`/`AD` records are
  **excluded** from the VAF list (biallelic-only, mirroring germline); indels included.
  Tech-plan may refine (e.g. split multiallelics) but RED tests can be written against the
  biallelic-only default now.

## Out of Scope

- **Strelka2-native VAF** (tier-count derivation `AU/CU/GU/TU`, `TAR/TIR`). Non-Mutect2
  VCFs degrade to UNVERIFIED. Deferred.
- **Second-caller concordance** (Strelka2 vs Mutect2) — that is the C1 somatic hook,
  a separate deferred slice (`CAPABILITY_ROADMAP.md:299`).
- **FAIL severity** for any somatic plausibility check (deferred until bands calibrated).
- **A somatic `FailureClass` / detector-corpus case** — plausibility is not a failure
  class; no detector change here (matches the RNA-seq plausibility slice, `CHANGELOG.md:283`).
- **Real nf-core/sarek run in CI**, PON/germline-resource reference wiring for a live
  Mutect2 run (that is a separate C4 launch-side deferral, `CHANGELOG.md:38-41`), and any
  dashboard/HTML bespoke UI beyond what the QCResult already renders.
- **Any Layer-1 / clinical interpretation.**
