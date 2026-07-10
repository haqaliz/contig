# Understanding — annotation-plausibility (C7 M2 + M3)

Phase-2 dig for `feat/annotation-plausibility/aliz`. Synthesizes two read-only agent
passes (code map + PRD/roadmap requirements digest). Grounded in file:line; no code
changed.

## What the work is really asking

Extend the shipped C7 annotation assay (M1, v0.25.0) along two more of its planned
verification axes, staying strictly Layer-2 research-use:

- **M2 (small):** make the *existing* M1 structural verifier + `AnnotationProvenance`
  capture also fire for the `somatic_variant_calling` assay. Per PRD "should-have" and
  roadmap L618-619 this is a **gate only, reusing M1 logic** — no new verification code.
- **M3 (the meat):** a new C3-style **annotation-plausibility** pack for *both* germline
  `variant_calling` and somatic `somatic_variant_calling`. Two WARN-capped checks:
  1. **annotated-fraction band** — share of variants receiving *any* consequence.
  2. **consequence-type distribution sanity** — flag an implausible distribution; the
     only worked example in the PRD is "refuse a ~100%-intergenic distribution."
  WARN-capped, uncalibrated defaults, **UNVERIFIED-when-absent, FAIL explicitly out of
  scope** (PRD Out-of-Scope + R3; M1 plan global constraint: max severity `warn`).

Research-use bright line (USE_CASE_UNIVERSE L33-54, 75-78): a verdict means "the
annotation ran correctly and reproducibly," **never** a pathogenicity/clinical judgement.
The consequence-distribution check is a *statistical sanity* signal ("does this look like
a real annotation run"), never a per-variant biological claim.

## Affected code (the map)

| Concern | File:line | M2/M3 role |
|---|---|---|
| M1 structural verifier | `src/contig/verification/annotation_structural.py:56-161` | M2 reuses as-is; exposes `_open_text`/`_declared_key`/`_record_has_key` (`:34-53`) M3 reuses |
| `_discover_qc` assay gates | `src/contig/runner.py:106-226` | M2 extends germline annotation gate (`:144-153`) to somatic; M3 adds new plausibility blocks |
| Germline annotation gate | `runner.py:144-153` (`if assay == "variant_calling"`) | M2: widen to `assay in ("variant_calling","somatic_variant_calling")` |
| Somatic plausibility gate (prior art) | `runner.py:161-195` (`if assay == "somatic_variant_calling"`) | M3 somatic block mirrors this |
| Plausibility-pack machinery | `rule_pack.py:235-349` | M3 adds `ANNOTATION_PLAUSIBILITY_PACK` (WARN-capped, NOT registered in `_RULE_PACKS`) |
| Somatic plausibility wrapper (template) | `somatic_plausibility.py:224-281` | exact evaluator pattern for M3: `computable` → `evaluate()` → explicit `unverified` loop |
| AnnotationProvenance model | `models.py:206-216, 297` | M2 gating question (capture is currently UNconditional) |
| Provenance parse/attach/render | `bundle.py:113-149`; `self_heal.py:1266`; `methods.py:81-90,137` | `_finalize` capture at `self_heal.py:1266` is not assay-gated today |
| Registry entries | `registry.py:24-48` | germline `default_params={"tools":"haplotypecaller,vep"}`; somatic `{"tools":"strelka,mutect2"}` (**no vep**) |
| Output manifests | `structural.py:244-284` | both assays resolve `.required[0]` → `"*.vcf.gz"` |
| Tests | `tests/verification/test_*plausibility.py`, `tests/verification/test_annotation_structural.py`, `tests/test_annotation_*.py` | M3: new `test_annotation_plausibility.py` + integration for both assays |

**Established idiom to mirror** (every plausibility wrapper): compute a `by_metric` dict,
filter to `computable = {m:v for m,v in by_metric.items() if v is not None}`, run
`evaluate({label: computable}, PACK)` (which *silently skips* absent metrics), then a
second loop emits an explicit `QCResult(status="unverified", value=None, kind="metric")`
for every uncomputable metric — that second loop **is** the never-a-false-pass guarantee.
Plausibility checks use `kind="metric"`; M1's structural checks use `kind="structural"`.

## Ambiguities / open questions for the interview (Phase 3)

These are gaps/under-specifications, **not** PRD↔roadmap contradictions (the two docs are
near-verbatim aligned). Ordered by how much they change the plan:

1. **M2 enablement vs. gate-only (latent tension).** The docs say M2 is "new assay gate
   only," but the somatic registry entry has **no `vep`** in its tools string
   (`{"tools":"strelka,mutect2"}`). Without enabling annotation on the somatic assay,
   sarek never emits an annotated somatic VCF, so the gated verifier would *always* report
   UNVERIFIED. Decision: does M2 also add `vep` to the somatic `default_params` (and if so,
   the exact sarek-somatic `--tools` string), or ship gate-only and accept UNVERIFIED until
   a live-cache follow-on? (Same live-cache caveat as M1: sarek may need `--vep_cache` /
   `--step annotate`; both verifiers degrade to UNVERIFIED honestly, so CI is unaffected.)

2. **Which somatic VCF carries the annotation** (Mutect2 vs Strelka2), and the selection/
   dedup rule. M1's germline gate takes the *first* VCF whose header declares CSQ/ANN and
   `break`s; the somatic assay emits multiple VCFs, so "first annotated wins" may be
   nondeterministic. The somatic-plausibility block already selects Mutect2 by a `mutect2`
   path component (`runner.py:169-176`) — reuse that convention?

3. **`annotated-fraction band` (M3) vs. `annotation_complete` (M1) overlap.** M1 already
   ships `annotation_complete` = fraction of records carrying the CSQ/ANN *field*. If M3's
   "annotated fraction" is the same quantity, it is redundant and trivially ~1.0 for a VEP
   run (every variant gets *some* consequence). Decision: M3's band must guard a *different*
   quantity — e.g. share of records whose consequence term is **non-empty / non-intergenic**
   — or the band is dropped and M3 is just the distribution-sanity check.

4. **Concrete consequence-distribution rule** (must be testable on synthetic fixtures with
   no real data). Only "~100%-intergenic" anchors it. Likely default: a single WARN on an
   **intergenic-fraction ceiling** (or a coding-fraction floor), uncalibrated. Decide the
   one shipping default rule.

5. **CSQ/ANN parser contract** (designed nowhere yet — M1 only detects field *presence*).
   VEP `CSQ`: pipe-delimited subfields whose order is defined by the `Format:` string in the
   `##INFO=<ID=CSQ,...Format: ...>` header (consequence at a header-resolved index; one
   comma-separated entry per transcript/allele; consequences can be `&`-joined). SnpEff
   `ANN`: fixed pipe layout, consequence in the `Annotation` field. Decide: header-driven
   index for CSQ + fixed position for ANN, and the **per-variant aggregation policy**
   (worst/most-severe consequence? count every transcript entry?). Reuse
   `annotation_structural`'s `_open_text`/`_declared_key`; add the subfield splitter locally
   (per the codebase's deliberate no-shared-VCF-lib convention).

6. **M3 "both assays" together vs. germline-first.** Roadmap says M3 covers both assays but
   also that milestones are germline-first. Confirm M3 ships germline+somatic plausibility
   in one slice (M2 lands the somatic gate just before, so both-at-once is consistent).

## Explicitly deferred (do NOT scope-creep)

- **M4** VEP-vs-SnpEff cross-tool annotation concordance — M3 must NOT do concordance.
- **M5** "corroborated by" surface + eval fold-in.
- **Research prioritization** (ACMG/PGx/PRS) — this initiative is verify-only.
- **FAIL-severity** annotation bands (until real-data calibration) — keeps M3 WARN-capped.
- Non-sarek / standalone annotation pipeline; trained classifier models.

## Guardrail check

On-thesis: pure Layer-2 verification over VCF INFO fields, no new tool run (no Layer-1
authoring), no proprietary data, gets better as VEP/SnpEff improve. No clinical claim. No
wet-lab/clinical credential precondition. Clears all four `CLAUDE.md` constraints.
