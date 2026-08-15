# Issue Card: annotation-cache-wiring (C7 enablement on real runs)

## Brief (inline, from the contig-next recommendation)

C7's verification axes (annotation structural, plausibility, VEP-vs-SnpEff
concordance, provenance) are all shipped but the annotation step may never run on
a real sarek run because Contig doesn't wire a VEP/SnpEff cache
(`--vep_cache`/`--download_cache`) or a `--step annotate` entry point — so
everything degrades to UNVERIFIED and the whole C7 value is hollow on real data.
Wire the enablement through the shipped `default_params` seam (surviving
rerun/resume, user's own `--tools` still wins), verify the annotated VCF is
produced, and keep every failure path an honest UNVERIFIED. Caveat: resolve the
correct sarek 3.5.1 mechanism (cache flag vs `--step annotate`) before choosing —
no real sarek run exists in CI, so confirm against sarek's documented behavior and
fixtures, test-first, no new dependency.

## Why (from the contig-next pick)

- Every C7 slice (M1–M5, all marked SHIPPED) inherits this live-cache caveat — the
  deepest "shipped but not turnkey" gap in the roadmap. The verification axes exist
  but the annotated VCF may never be produced on a real run.
- Follow-on slice of a shipped capability (contig-next rule 6): making the shipped
  verify capability actually fire widens what the verified verdict covers on real
  data, and real annotation runs feed plausibility/concordance outcomes into the
  shipped `verify-case-promote` corpus channel (C6) — deepening moat #2.
- Unblocked: the enablement seam already exists — `default_params` injection that
  survives rerun/resume (shipped M1/M2), and every failure path degrades to an
  honest UNVERIFIED, never a false pass.

## Sources in the roadmap

- `docs/technical/CAPABILITY_ROADMAP.md` C7 (M1 slice): "a real run's annotation
  step may still require a VEP/SnpEff cache (`--vep_cache`/`--download_cache`) or a
  `--step annotate` entry point that Contig does not yet wire — when that annotation
  output is absent the verifier reports UNVERIFIED, so a missing cache surfaces
  honestly rather than as a silent success."
- Same caveat carried by M3 (annotation plausibility) and M4 (VEP-vs-SnpEff
  concordance): "Same carried live-cache caveat as M1."
- C7 M1/M2: the `default_params` seam ("injected non-destructively — a user's own
  `--tools` wins — and re-injected on rerun/resume") is the mechanism this slice
  extends.

## Task source

Inline brief (no GitHub issue filed for this slug). Owner: aliz.
