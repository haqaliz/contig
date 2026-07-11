# Understanding — rnaseq-mapping-composition-plausibility (Phase 2 dig)

Source: `_card/issue.md` brief + two read-only dig agents + on-disk real-run inspection.
Date: 2026-07-11. Worktree baseline: 1452 passed, 1 skipped.

## What the work is really asking

Add a **C3 biological-plausibility** signal for the RNA-seq assay that measures where
aligned reads fall relative to gene annotation — the **exonic / intronic** read-fraction
composition — and surfaces it as a WARN-capped verdict check. Low exonic fraction (or
high intronic) is a classic smell for genomic-DNA contamination, failed poly-A / rRNA
depletion, or a broken annotation, and no incumbent issues this as a correctness signal.
It is the "exonic-mapping fraction" item named but unbuilt in the C3 RNA-seq list
(`CAPABILITY_ROADMAP.md:397`) and explicitly deferred by the v0.6.0 rnaseq slice
(`docs/planning/rnaseq-plausibility/prd.md:93`).

## The feasibility fork — RESOLVED (this was the caveat to dig first)

The brief flagged one load-bearing question: is the composition signal reachable from a
default Contig rnaseq run, and via MultiQC or a dedicated parser? **Resolved by inspecting
real runs on disk (`runs/testpass2`, `runs/test-2026-06-21T22-18-14-239Z`):**

1. **The RSeQC `read_distribution` artifact IS produced by default** at
   `results/star_salmon/rseqc/read_distribution/<sample>.read_distribution.txt`
   on nf-core/rnaseq@3.26.0 (the pinned revision, `registry.py:15-16`). Confirmed on 4+
   real runs. So no launch-param change is needed to make the artifact exist.
2. **The composition fractions do NOT reach Contig's MultiQC ingest.** Contig reads only
   `report_general_stats_data` from `multiqc_data.json` (`qc_ingest.py:7`). A real run's
   general-stats block has 11 metric keys, **none** exonic/intronic/CDS/tag-related, and
   there is no read-distribution section Contig parses. Extending the existing
   MultiQC-fed `RNASEQ_PLAUSIBILITY_PACK` path would therefore only ever emit UNVERIFIED.

**Decision: dedicated stdlib parser of the RSeQC artifact** — exactly the shipped
fires-slice pattern (methylseq/ampliseq/mag). The caveat from the handoff is retired
favorably: the artifact is default-present, so the check will genuinely fire, not no-op.

## The real read_distribution.txt format (from a run on disk)

```
Total Reads                   142111
Total Tags                    146154
Total Assigned Tags           129802
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           146030              129779              888.71
5'UTR_Exons         0                   0                   0.00
3'UTR_Exons         0                   0                   0.00
Introns             530                 23                  43.31
TSS_up_1kb          43552               0                   0.00
TSS_up_5kb          76907               0                   0.00
TSS_up_10kb         89031               0                   0.00
TES_down_1kb        40737               0                   0.00
TES_down_5kb        81271               0                   0.00
TES_down_10kb       97060               0                   0.00
=====================================================================
```
(This is the nf-core rnaseq yeast test profile — CDS-dominated, expected.)

**Metric computation (over the `Tag_count` column):**
- `exonic_fraction` = (CDS_Exons + 5'UTR_Exons + 3'UTR_Exons) / **Total Assigned Tags** —
  the mRNA-enrichment signal. WARN **below** a lenient threshold.
- `intronic_fraction` = Introns / Total Assigned Tags — WARN **above** a lenient threshold
  (pre-mRNA / gDNA contamination). Candidate; may ship informational.
- **TSS_up_/TES_down_ bins are nested & overlapping windows (1kb ⊂ 5kb ⊂ 10kb)** — they
  must NOT be summed into an "intergenic" number (double-counts). A clean intergenic-ish
  signal, if wanted, is the *unassigned* fraction: `(Total Tags − Total Assigned Tags) /
  Total Tags`. This is a PRD decision (see open questions).

## How it wires in (from the code dig)

- **New parser** `src/contig/verification/rnaseq_metrics.py`: stdlib-only, pure,
  `parse_read_distribution(path) -> dict[str, float]` returning `{exonic_fraction: …,
  intronic_fraction: …}`; omit any metric it can't compute (never coerce to 0); guard
  `Total Assigned Tags == 0`. Mirrors `methylseq_metrics.py` (one file → one sample).
- **New locator** `_locate_rnaseq_composition_qc(run_dir)` in `runner.py`: rglob
  `*.read_distribution.txt`, derive sample id by stripping the `.read_distribution` suffix,
  return `{sample: {slug: value}}`; a located-but-unparseable file → empty dict for that
  sample (→ explicit UNVERIFIED at the gate).
- **New gate block** in `runner._discover_qc` (`runner.py`, alongside the existing
  `assay == "rnaseq"` plausibility gate at `:347-349`), copied from the methylseq template
  (`runner.py:385-400`): evaluate `RNASEQ_COMPOSITION_PACK` when metrics present, else emit
  one `rnaseq_composition_qc:<sample>` UNVERIFIED. **No artifact at all → silent skip**
  (structural QC owns genuinely-missing outputs; read_distribution is not in the rnaseq
  structural manifest, `structural.py:245-249`, and must stay out of it).
- **New rule pack** `RNASEQ_COMPOSITION_PACK` in `rule_pack.py`, WARN-capped (no `fail_*`),
  **not** registered in `_RULE_PACKS` (matches the other plausibility packs).
- **`rnaseq` stays OUT of `_DEDICATED_METRIC_ASSAYS`** (`runner.py:67`): the existing
  `RNASEQ_RULE_PACK` alignment/assignment checks still need the generic MultiQC path
  (`runner.py:245-248`). The new gate is purely additive.
- **Tests**: `tests/verification/test_rnaseq_metrics.py` (inline-string fixtures via a
  local `_write(tmp_path,…)` helper, plain text — the house style) + a committed realistic
  `tests/fixtures/rnaseq/<sample>.read_distribution.txt` (new dir; author from a real run,
  sanitized) + gate assertions in `tests/verification/test_run_qc.py`. **No real nf-core
  run in CI.**

## Honest contract (matches every sibling C3 slice)
- WARN-capped bands, uncalibrated engineering defaults, **no FAIL** until real-data
  calibration. UNVERIFIED (never a false pass) when the artifact/metric is absent.
- Additive to the verdict only: no new `FailureClass`, model, persisted-record, or
  dependency; no exit-code change; `eval-guard`/`heal-guard` baselines untouched.
- Local, deterministic, **no raw-read egress** (parses a small QC text file already on the
  user's compute).

## Guardrail check (CLAUDE.md)
Squarely Layer-2 verify-layer work ("make every verdict harder to fool"). Not Layer-1.
No wet-lab/clinical credentials. Research-use sanity signal, never a clinical judgement.
**No drift detected.**

## Open questions for the requirements interview
1. **Metric set.** Ship `exonic_fraction` alone (tightest, clearest), or also
   `intronic_fraction` and/or the `unassigned_fraction` intergenic-ish signal? Which get
   WARN bands vs. informational-only?
2. **Denominator.** Total Assigned Tags (excludes off-annotation) vs. Total Tags. Exonic
   over Assigned is the cleaner enrichment ratio; Total Tags folds in the unassigned smell.
3. **Band values.** Lenient defaults so a normal run reads PASS — e.g. `exonic_fraction`
   warn_below ~0.50? These are uncalibrated; state them as engineering defaults.
4. **Multi-sample.** read_distribution is one-file-per-sample; confirm per-sample checks
   (like the other packs) with no cross-sample aggregation this slice.
5. **Naming.** Check names (`exonic_fraction`, …) and the located-but-empty UNVERIFIED key
   (`rnaseq_composition_qc:<sample>`).
6. **Scope guard.** Gene-body-coverage evenness stays deferred (needs the non-default
   `geneBody_coverage` module); FAIL severity deferred to real-data calibration; no
   dashboard card this slice unless trivial.
