# Card: feat / assay-qc-verdict-fires

- **Type:** feat
- **Id/slug:** assay-qc-verdict-fires
- **Owner:** aliz
- **Branch:** feat/assay-qc-verdict-fires/aliz
- **Source:** inline brief (no GitHub issue; carried from a `/contig-next` recommendation, 2026-07-11)

## Brief

Harden the biological verdict for the methylation (`methylseq`), 16S-amplicon
(`ampliseq`), and shotgun-metagenomics (`mag`) assays so their QC packs actually
**fire** on a real run — the direct sibling of the shipped single-cell fix
(v0.21.0). Lead with **methylseq** as the first slice; ampliseq and mag are
fast-follows on the same seam.

Today `METHYLSEQ_RULE_PACK` / `AMPLISEQ_RULE_PACK` / `MAG_RULE_PACK`
(`src/contig/verification/rule_pack.py:131-226`) draw their metrics **only** from
`parse_multiqc_general_stats_file` (via `runner.py:_discover_qc` → `run_qc.py`),
using metric slugs the source itself annotates as **"slug unverified"** on nearly
every entry. Because `evaluate()` silently skips any absent metric, a wrong slug
degrades every check to UNVERIFIED with **no breadcrumb** — so three of the seven
wired assays are effectively verdict-hollow, "reading as wired" while never firing.
This is the exact latent no-op that hollowed out the single-cell verdict until
v0.21.0.

## Proposed first slice (methylseq)

1. Confirm the **real** Bismark MultiQC general-stats slugs (bisulfite conversion,
   mapping efficiency, duplication) from a **realistic captured `multiqc_data.json`
   fixture** — CI never runs nf-core/methylseq, so build a realistic fixture rather
   than guessing keys (in-pattern: commit `5cedaaa` did this for sarek annotation).
2. Add a **tolerant key lookup** (alias set per metric) so the pack keys off the
   actual slug(s).
3. Emit an **explicit `<check>:<sample>` UNVERIFIED** breadcrumb when a MultiQC file
   is located but lacks the expected metric — never a silent no-op (mirror the
   scrnaseq "located-but-unparseable → explicit UNVERIFIED" pattern).
4. Keep the packs **WARN/FAIL-capped and UNVERIFIED-when-absent** exactly as today;
   **no band re-calibration** (bands stay illustrative engineering defaults, since
   FAIL-severity calibration on real data is a separately-deferred concern).

Then repeat for **ampliseq** (DADA2 read-retention / ASV count / read depth) and
**mag** (QUAST N50, CheckM completeness/contamination) on the same seam.

## Why (moat grounding)

- Pure **C3 biological-plausibility verification**
  (`docs/technical/CAPABILITY_ROADMAP.md:330-392`): Layer-2 only, makes the verdict
  "smarter about biology," and each firing check adds plausibility eval data.
- Matches `CLAUDE.md`: seven assays "wired and being hardened to the same bar" as
  RNA-seq — this closes that gap for three of them.
- Low feasibility risk: v0.21.0 scrnaseq slice is a proven template.

## Distinction from a DEFERRED sibling (keep the caveat honest)

This is **not** the deferred single-cell *simpleaf/alevin-fry* ingestion. That path
is blocked because the default aligner emits **no structured artifact at all** (HTML
AlevinQC / evolving QCatch). Bismark/DADA2/QUAST **do** write structured MultiQC
general-stats — so this is a solvable **slug-accuracy** problem against an existing
artifact, not a missing-source blocker.

## Known caveat / risk to dig first

The whole slice hinges on getting the **actual MultiQC general-stats keys right**,
and CI never runs these nf-core pipelines. Plan to build/obtain a realistic
`multiqc_data.json` fixture (real nf-core test-profile output structure) before
locking slugs — guessing keys reintroduces the same silent-no-op it's meant to fix.

## Constraints (from CLAUDE.md)

- Layer-2 only (run / self-heal / verify / reproduce). No Layer-1 workflow authoring.
- No raw-read egress — parsers read small summary files on the user's compute.
- No correctness over-claiming — UNVERIFIED never rendered as PASS; bands scoped per
  assay, uncalibrated defaults stay WARN/FAIL-capped.
- Test-first (strict TDD), synthetic/realistic fixtures — no real nf-core run in CI.
