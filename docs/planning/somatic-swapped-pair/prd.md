# PRD: somatic-swapped-pair (tumor/normal swap smell test)

Status: draft for review. Owner: aliz. Branch: `feat/somatic-swapped-pair/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff), `_card/understanding.md`
(Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md` C4. Capability: **C4 follow-on**
(the deferred "cross-column swapped-pair smell test" named at
`somatic-strelka2-vaf/prd.md:175` and `somatic-vaf-plausibility/vaf-verdict/plan_20260704.md:25`).

## Problem Statement

Contig's somatic (tumor–normal) verdict reads variant allele fraction **only from the tumor
column** of the run's Mutect2 VCF (`verification/somatic_plausibility.py`, v0.14.0). When the
tumor and normal samples are **swapped or mislabeled** — a sample-sheet mixup, a swapped
aliquot, or heavy tumor-in-normal contamination — the somatic caller runs to "success" and
the researcher reports **the normal's germline variants as the tumor's somatic mutations**
(or misses the real somatic signal entirely). The run passes structural QC (outputs exist),
passes the tumor-VAF band (a swapped normal-as-tumor still has plausible-looking VAFs), and
returns a biologically inverted result **with no error**.

This is a notorious, catastrophic, silent-failure class in somatic analysis, and it is
exactly the moat (`CLAUDE.md`: "make every verdict harder to fool"). No incumbent (Galaxy,
Terra, Seqera, DNAnexus) issues an output-correctness verdict, let alone one that catches a
sample swap (`FEATURES.md:61-68`).

**Evidence it's real:** the deferral notes that parked this slice
(`somatic-vaf-plausibility/vaf-verdict/plan_20260704.md:25-33`) call it a
"documented residual risk" — low-probability but real, deliberately left for a separate
slice, *not* blocked. The tumor/normal swap is a standard item on somatic-QC checklists
precisely because it is invisible to every downstream check.

## Goals & Success Metrics

- **G1 — Catch a swapped/mislabeled normal at verify time.** A somatic run whose **normal**
  column carries an implausibly high median VAF (the somatic signal is in the normal, or the
  normal *is* a tumor) emits a **WARN** `normal_median_vaf:<NORMAL>` check on the verdict.
  *Metric:* a fixture with a high-VAF normal column yields exactly one WARN check naming the
  normal median VAF; a fixture with a ~0 normal column yields PASS.
- **G2 — Zero false alarms on a legitimate pair.** A correct tumor/normal pair (normal VAF
  ~0 at somatic sites, benign low-level contamination < 0.30) reads **PASS**. *Metric:* a
  realistic-normal fixture (median normal VAF ≤ 0.10) passes; no existing somatic test
  regresses.
- **G3 — Honest UNVERIFIED, never a false pass.** When the normal column cannot be resolved
  (no `##normal_sample=` header, or no matching `#CHROM` column, or no derivable normal VAF),
  the check is **UNVERIFIED**, never PASS and never silently dropped. *Metric:* a VCF whose
  `##normal_sample=` header is stripped yields one `unverified` check.
- **G4 — Additive, no regression, no network, no tool exec.** The full suite stays green;
  the check is pure local VCF parsing; **never changes the `contig run`/`verify` exit code**.

## User Personas & Scenarios

- **A, lone computational biologist:** runs a somatic cohort; one PI's tumor/normal aliquots
  were swapped at intake. Today she reports germline SNPs as somatic drivers and finds out
  only if a reviewer notices. Wants the tool to flag the inverted pair before she trusts it.
- **C, core facility:** processes many tumor/normal pairs for many PIs; wants a consistent,
  automatic swap guard so a labeling error in one batch surfaces on the verdict, not in a
  retraction.

## Requirements

### Must-have

- **R1 — `normal_median_vaf` metric.** Median VAF over the **normal** column, computed in the
  **same single record pass** as the tumor `median_vaf` (same biallelic Mutect2 records, not
  a separate scan and not filtered differently), reusing the shipped `_vaf_from_sample`
  (FORMAT `AF`, else `AD_alt/DP`) unchanged — only the sample column index differs. If the
  normal VAF list is empty (no biallelic record yields a derivable normal VAF), the median is
  `None` → UNVERIFIED (R4), mirroring the tumor half's empty-`vafs` handling — a tiny/near-
  empty call set never WARNs on noise.
- **R2 — `##normal_sample=` → column resolver.** A new resolver mirroring
  `_tumor_column_index`/`_tumor_sample_name` (`somatic_plausibility.py:59-78,191-196`):
  parse `##normal_sample=<name>`, match it to a `#CHROM` column. **Never guess a column** —
  missing header or no match → `None` → UNVERIFIED (R4). **Single-pair posture:** resolve the
  single `##normal_sample=` (first, mirroring the tumor half's first-sample handling); a
  multi-pair or tumor-only layout that yields no unambiguous normal column → UNVERIFIED, never
  a positional guess. (Header spelling confirmed against a real GATK Mutect2 header as the
  first implementation task — see Risks.)
- **R3 — One WARN-capped rule on the existing pack.** Add `normal_median_vaf` to
  `SOMATIC_PLAUSIBILITY_PACK` (`rule_pack.py:296-328`) with **`warn_above: 0.30` only** — no
  `warn_below` (a low normal VAF is the healthy expected case), **no `fail_*`** (uncalibrated
  engineering default). Pack stays unregistered in `_RULE_PACKS`.
- **R4 — Honest contract, identical to every sibling C3/C4 slice.** At most WARN, never FAIL,
  never changes the exit code. UNVERIFIED (never a false pass) when the normal column is
  unresolvable or no normal VAF is derivable; **no Mutect2 VCF at all → silent skip**
  (structural QC owns a genuinely-missing output; matches the `if vcfs:` gate at
  `runner.py:340`).
- **R5 — `by_metric` isolation.** A new `evaluate_swap_plausibility(vcf, sample=None)` builds
  `by_metric = {"normal_median_vaf": value}` and drives the shared `evaluate(...)` so **only**
  that rule fires — the existing `median_vaf`/`somatic_variant_count`/`strelka_median_vaf`
  rules are never re-emitted (the v0.34.0 Strelka precedent, `strelka_vaf.py:244-252`; relies
  on `evaluate()` skipping absent metric keys, `rule_pack.py:474-475`). Emits
  `normal_median_vaf:<NORMAL>`.
- **R6 — Runner wiring.** Slot the evaluator into the existing
  `if assay == "somatic_variant_calling":` block (`runner.py:337-407`), on the
  **already-globbed** Mutect2 VCF (reuse `select_caller_vcfs(run_dir, vcfs)`,
  `somatic_concordance.py:164-211`, already called at `runner.py:387` — do not re-glob).

### Should-have

- **S1 — Message clarity.** The WARN message names the signal plainly (e.g. "normal-sample
  median VAF is high — possible tumor/normal swap, mislabel, or contamination") so a
  non-expert (persona B/C) understands *why* without reading VCF internals.

### Nice-to-have (explicitly deferred, see Out of Scope)

- Directional tumor-vs-normal delta as a second corroborating signal.
- FAIL severity once the band is calibrated on real cohorts.

## Technical Considerations

- **Where it sits:** verify stage only (`_discover_qc` → `run_qc`). Additive to the verdict;
  no change to run/self-heal/reproduce.
- **Reuse, don't re-glob:** the Mutect2 VCF is already located in the runner block via
  `select_caller_vcfs`; the new evaluator receives that path.
- **Reader generalization:** `_read_somatic` (`somatic_plausibility.py:122-163`) currently
  reads the tumor index; generalize it to accept a target column index (or add a sibling
  normal reader) so tumor and normal VAF derivation share one code path.
- **No new dependency, model, `FailureClass`, persisted record, or reproduce-contract
  change.** Stdlib only (`gzip`, `statistics.median`). No raw-read egress (reads a small VCF
  already on the user's compute). Research-use corroboration, never a clinical/cancer verdict.
- **Test-first:** synthetic two-column (NORMAL/TUMOR) VCF fixtures written to `tmp_path`;
  fixtures already model a populated NORMAL column (`test_somatic_plausibility.py:21-41`) —
  extend `_header` to inject `##normal_sample=`. No real nf-core/sarek or GATK run in CI.

## Risks & Open Questions

- **R-1 (pin FIRST): `##normal_sample=` header spelling is unverified in this codebase.** No
  `src/` code parses it today; real GATK Mutect2 emits it symmetric to `##tumor_sample=`, but
  confirm the exact spelling against a real sarek 3.5.1 Mutect2 header before coding the
  resolver. **Mitigation:** the UNVERIFIED-when-absent floor (R4) absorbs a wrong assumption —
  a stripped/re-headed VCF simply degrades, never false-passes; `_pon_status` already models
  this posture.
- **R-2 (accepted): the band is uncalibrated.** `warn_above: 0.30` is a loose engineering
  default chosen for wide headroom over benign low-level (< 0.30) normal contamination.
  FAIL severity and real-cohort calibration are out of scope (accepted, WARN-only).
- **R-3 (accepted): detection is via the VAF-direction signal, not label inspection.** A
  sheet-level swap that is internally label-consistent is caught only because the normal
  column then carries the somatic signal — which is the point. A swap that leaves both
  columns with plausible VAFs (rare) is not caught; documented as residual risk, honestly.
- **Open:** should the WARN message distinguish "swap" from "contamination"? They're
  indistinguishable from VAF alone — the message should name both possibilities, not commit
  to one (folds into S1).

## Out of Scope (confirmed deferred)

- **FAIL severity + real-cohort band calibration** (metric stays WARN-capped).
- **A directional tumor-vs-normal ratio/delta** (the warn-above-only metric catches a
  superset; a ratio adds a divide-by-~0 edge in the healthy case).
- **PON / germline-resource reference wiring** for a real Mutect2 somatic run.
- **Strelka2-native normal VAF** (Strelka2's normal-column tier derivation — a possible
  follow-on, but this slice is Mutect2-only to match the tumor `median_vaf` it extends).
- **A dashboard card / "corroborated by" surface** for the swap signal.
- **Any `FailureClass`, self-heal, or eval-corpus/heal-scenario change.**
- **Any Layer-1 (NL→workflow) surface.**
