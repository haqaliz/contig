# Card: feat / germline-sex-check-plausibility

- **Type:** feat
- **Id/slug:** germline-sex-check-plausibility
- **Owner:** aliz
- **Branch:** feat/germline-sex-check-plausibility/aliz
- **Source:** inline brief (no GitHub issue; carried from a `/contig-next` recommendation, 2026-07-11)

## Brief

Build a C3 germline biological-plausibility slice that infers **karyotypic sex**
from the run's own VCF (X-chromosome heterozygosity ratio and Y-chromosome
variant presence) and adds a WARN-capped `sex_plausibility` check to the germline
verdict, gated to `assay == "variant_calling"` in `_discover_qc`, reusing the
shipped `verification/variant_metrics.py` VCF-parsing path rather than a new
compute path.

Honest contract, identical to the other C3 slices:
- at most WARN (never FAIL),
- never changes the `verify` exit code,
- **UNVERIFIED — never a false pass** whenever the karyotype signal is ambiguous
  or the Y contig is absent from the reference.

## Caveat to carry in (dig this first)

"Reported sex" is **not** a Contig input today — sample sheets carry no sex
column — so this slice's signal is inferred-sex *sanity*, not reported-vs-inferred
concordance. That concordance (and the sample-sheet sex column it needs) is a
deliberate follow-on, **out of scope** here. Inferred sex from variant data is a
known-imperfect signal (low coverage, XXY/XYY, no Y contig in the reference), so
it must be WARN-capped, never FAIL, per the standing no-over-claiming rule.

Test-first with synthetic gzipped VCF fixtures (a male-pattern X/Y, a
female-pattern, and an ambiguous/low-signal case); no real sarek run in CI.

## Provenance (contig-next ranking, 2026-07-11)

Picked as the single highest-leverage next feature because:
- Named, unbuilt C3 slice: `docs/technical/CAPABILITY_ROADMAP.md:378` lists
  "sex-check concordance between reported and inferred sex"; explicitly deferred
  in the RNA-seq slice at `:347`.
- Germline (`variant_calling`) is the assay exercised end-to-end in CI (`CLAUDE.md`).
- Reuses the shipped `verification/variant_metrics.py` VCF path (same input as
  `ts_tv`/`het_hom`) — no new compute path (unlike gene-body-coverage's RSeQC
  blocker).
- Unblocked, unlike its neighbours: single-cell mito/doublet need a scanpy step;
  the C5 assembly-signature detector is blocked on the missing sample-side contig
  signal (v0.7.0 changelog); the C6 eval fold-in is blocked on a labeling design.

## Constraints (from CLAUDE.md)

- Layer-2 only (run / self-heal / verify / reproduce). No Layer-1 workflow authoring.
- No raw-read egress — the parser reads the small VCF already on the user's compute.
- No correctness over-claiming — UNVERIFIED never rendered as PASS; a research-use
  sanity signal, never a clinical sex/karyotype determination.
- Test-first (strict TDD), synthetic fixtures — no real nf-core/sarek run in CI.
