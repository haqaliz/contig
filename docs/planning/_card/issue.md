# Card: feat / rnaseq-mapping-composition-plausibility

- **Type:** feat
- **Id/slug:** rnaseq-mapping-composition-plausibility
- **Owner:** aliz
- **Branch:** feat/rnaseq-mapping-composition-plausibility/aliz
- **Source:** inline brief (no GitHub issue; carried from a `/contig-next` recommendation, 2026-07-11)

## Brief (from contig-next)

Add a new **C3 biological-plausibility** check for the **RNA-seq** assay: an
**exonic-mapping-fraction** (and intronic / intergenic composition) sanity signal,
ingesting the RSeQC **read-distribution** artifact produced by an `nf-core/rnaseq` run.

**Why this pick (moat grounding):**
- On-list, unshipped, depth-first on the one CI-validated assay. `CAPABILITY_ROADMAP.md`
  C3 RNA-seq build list (line ~397) names "exonic-mapping fraction", but the shipped
  RNA-seq slice (`CHANGELOG.md` v0.6.0) only landed `duplication_rate` +
  `rrna_contamination`. RNA-seq is the single assay exercised end-to-end in CI
  (`CLAUDE.md`), so this deepens the verdict where it is most trustworthy rather than
  widening shallowly.
- Rides the hot, proven "make the check fire from the tool's own on-disk artifact" seam:
  `CHANGELOG.md` v0.21.0 (scrnaseq), v0.29.0 (methylseq / ampliseq / mag) — a dedicated
  `_discover_qc` gate + stdlib parser, WARN-capped, UNVERIFIED-when-absent.
- Pure moat, gets better with better models: "the verdict getting smarter about biology"
  (`CAPABILITY_ROADMAP.md:391-394`), captures a new per-assay plausibility distribution
  into the corpus (moat #2), strictly Layer-2 / local, no raw-read egress.

## Honest contract (matches every sibling C3 slice)
- WARN-capped bands, no FAIL until real-data calibration.
- UNVERIFIED (never a false pass) when the artifact/metric is absent.
- Additive to the verdict only: no new `FailureClass`, model, or persisted-record change;
  no new dependency; no exit-code change.
- Test-first with a committed fixture; **no real nf-core/rnaseq run in CI**.

## Caveat to carry in (dig this FIRST)

Confirm which read-distribution artifact a Contig `nf-core/rnaseq` run writes **by
default**, and whether the exonic / intronic / intergenic composition fractions already
reach **ingested MultiQC** (→ extend `RNASEQ_PLAUSIBILITY_PACK` on the existing MultiQC
path) or need a **dedicated parser** (→ a new `verification/rnaseq_metrics.py`-style gate,
mirroring the fires-slices). The UNVERIFIED-when-absent contract bounds the risk either
way — if the artifact is absent in a given run, the check degrades honestly rather than
mis-firing.

## Provenance (contig-next ranking, 2026-07-11)

Picked as the single highest-leverage next feature because:
- Named, unbuilt C3 RNA-seq slice (`CAPABILITY_ROADMAP.md:397`); v0.6.0 shipped only
  duplication + rRNA (`CHANGELOG.md`).
- RNA-seq (`nf-core/rnaseq`) is the assay exercised end-to-end in CI (`CLAUDE.md`).
- Rides the freshly-shipped assay-QC-fires seam (v0.21.0 / v0.29.0) — proven pattern,
  low novelty risk.
- Unblocked, unlike its neighbours: single-cell mito/doublet need a scanpy step; the C5
  assembly-signature detector is blocked on the missing sample-side contig signal
  (v0.7.0 changelog); the C6 eval fold-in is blocked on a labeling design;
  gene-body-coverage evenness is gated by a heavy non-default RSeQC compute path.

**Alternates considered:** CRAM↔BAM input-format conversion self-heal (C2 — highest
self-heal leverage but a weak live-trigger for a FASTQ-first tool); C6 held-out-accuracy
trend (clean/unblocked but lower-leverage flywheel instrumentation).

## Constraints (from CLAUDE.md)
- Layer-2 only (run / self-heal / verify / reproduce). No Layer-1 workflow authoring.
- No raw-read egress — the parser reads the small QC artifact already on the user's compute.
- No correctness over-claiming — UNVERIFIED never rendered as PASS; a research-use sanity
  signal, never a clinical judgement.
- Test-first (strict TDD), synthetic fixtures — no real nf-core/rnaseq run in CI.

## Baseline
- Worktree: `.claude/worktrees/feat-rnaseq-mapping-composition-plausibility`
- Branch: `feat/rnaseq-mapping-composition-plausibility/aliz` from `origin/master` (dee5ef4)
- Test baseline: **1452 passed, 1 skipped** (`uv run pytest`)
