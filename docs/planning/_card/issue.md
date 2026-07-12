# Card: feat / germline-variant-count-plausibility

- **Type:** feat
- **Id/slug:** germline-variant-count-plausibility
- **Owner:** aliz
- **Branch:** feat/germline-variant-count-plausibility/aliz
- **Source:** inline brief (no GitHub issue; carried from a `/contig-next` recommendation, 2026-07-12)

## Brief (from contig-next)

Add a **C3 biological-plausibility** check for the **germline** (`variant_calling`)
assay: a WARN-capped **expected-variant-count band** computed from the run's primary
germline VCF, gated to `assay == "variant_calling"` in `_discover_qc`, symmetric to the
shipped somatic `somatic_variant_count`.

It is the **last unbuilt item on the `CAPABILITY_ROADMAP.md` C3 germline build list**
(line ~421, "expected variant-count band for the assay"). The shipped germline C3 slices
are Ti/Tv + het/hom (`v0.3.0`) and the karyotypic sex-check (Unreleased/C3). A grep of
`src/contig/verification/` confirms `variant_count` exists **only** in
`somatic_plausibility.py` and `sex_plausibility.py` (`y_variant_count`) — germline has no
total-count band today.

**Why this pick (moat grounding):**
- On-list, unshipped, depth-first on the variant assay closest to the CI-exercised path.
  Finishes C3 depth for germline.
- Rides the proven C3 seam: a dedicated verification module + a WARN-capped rule pack +
  an additive `_discover_qc` gate, UNVERIFIED-when-absent. Symmetric to the shipped
  `somatic_plausibility.py` (`somatic_variant_count`).
- Pure moat, "the verdict getting smarter about biology"
  (`CAPABILITY_ROADMAP.md:410-413`); captures a new per-assay count distribution into the
  corpus (moat #2); strictly Layer-2 / local; **no raw-read egress** (reads a VCF already
  on the user's compute).

## Honest contract (matches every sibling C3 slice)
- WARN-capped band, **no FAIL** until real-data calibration.
- UNVERIFIED (never a false pass) when the VCF/metric is absent or uncomputable.
- Additive to the verdict only: no new `FailureClass`, model, or persisted-record change;
  no new dependency; **no exit-code change**.
- Test-first with a committed synthetic VCF fixture; **no real nf-core/sarek run in CI**.

## Caveat to carry in (dig this FIRST)

Variant count is strongly **capture/depth-dependent** — WGS vs WES vs a targeted panel
produce wildly different totals — so a single fixed band risks false WARNs. Recommend
slice 1 keep **one very-wide, catch-only-gross-failures band** (matching the loose,
uncalibrated WARN-cap convention of every prior C3 slice; FAIL/calibration deferred),
rather than conditioning on a capture signal Contig may not have. Also confirm the check
reuses the **same primary-germline-VCF locator** as `variant_metrics`/`sex_plausibility`
so the verdict and provenance can never disagree.

## Provenance (contig-next ranking, 2026-07-12)

Picked as the single highest-leverage **unblocked** next feature:
- Named, unbuilt C3 germline slice (`CAPABILITY_ROADMAP.md:~421`); germline has no
  total-count band (verified in code).
- Reuses the freshly-proven C3 verification-module + rule-pack + `_discover_qc`-gate
  pattern (somatic VAF slice, RNA-seq composition slice) — low novelty risk.
- Unblocked, unlike its neighbours: CRAM↔BAM self-heal has a weak live-trigger for a
  FASTQ-first tool; the C5 assembly-signature detector is blocked on the missing
  sample-side contig signal; the C6 eval fold-in is blocked on a labeling design;
  single-cell mito/doublet + RNA-seq gene-body-coverage need heavy non-default compute.

**Alternates considered:** C2 CRAM↔BAM input-format-conversion self-heal (highest raw
self-heal leverage but gated by a weak live-trigger — passed on by the last two
contig-next sessions); C6 held-out-accuracy trend (clean/unblocked but a narrow extension
of the already-shipped training-corpus trend, lower-leverage instrumentation).

## Constraints (from CLAUDE.md)
- Layer-2 only (run / self-heal / verify / reproduce). No Layer-1 workflow authoring.
- No raw-read egress — the check reads the small germline VCF already on the user's compute.
- No correctness over-claiming — UNVERIFIED never rendered as PASS; a research-use sanity
  signal, never a clinical judgement.
- Test-first (strict TDD), synthetic fixtures — no real nf-core/sarek run in CI.

## Baseline
- Worktree: `.claude/worktrees/feat-germline-variant-count-plausibility`
- Branch: `feat/germline-variant-count-plausibility/aliz` from `origin/master` (e8190a1)
- Test baseline: **1479 passed, 1 skipped** (`uv run pytest`)
