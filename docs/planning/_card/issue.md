# Card: feat / sc-concordance-autorun

- **Type:** feat
- **Id/slug:** sc-concordance-autorun
- **Owner:** aliz

No GitHub issue — this unit of work came from a `/contig-next` recommendation
(2026-07-12). Source of truth for the pipeline is the inline brief below.

## Brief

Build the single-cell concordance **autorun** `contig verify --concordance-sc-counts-auto`:
given `--reads <sample sheet>` and the needed index/whitelist, Contig runs a *second,
independent* single-cell quantifier itself behind an injectable seam (mirroring the RNA-seq
kallisto autorun in `verification/count_quantifier.py`, v0.24.0) and feeds its pseudobulk
gene totals into the already-shipped `stats_from_counts` core rather than requiring a
user-supplied second matrix.

This is the named follow-on to the user-supplied single-cell slice `--concordance-sc-counts`
shipped in **v0.32.0**, and it mirrors how the germline autorun `--concordance-auto` (v0.4.0)
followed `--concordance-vcf`, and the RNA-seq kallisto autorun `--concordance-counts-auto`
(v0.24.0) followed `--concordance-counts`. It is where the single-cell concordance axis
gains turnkey value (the v0.32.0 slice acknowledged single-cell users may not have a second
matrix on hand).

## Honest contract (standing concordance contract, non-negotiable)

- at most WARN, never changes the `contig verify` exit code,
- `unverified` (never a false pass) below the 10-shared-gene floor,
- the concordance flags are **mutually exclusive**: `--concordance-vcf`,
  `--concordance-auto`, `--concordance-counts`, `--concordance-counts-auto`,
  `--concordance-sc-counts`, and the new `--concordance-sc-counts-auto`.
- gated to `assay == "scrnaseq"`; every unrunnable path (non-scrnaseq run, missing
  `--reads`/`--index`, quantifier failure, malformed sample sheet) prints a clear skip
  note and emits zero checks — never a false pass.

## CI story (mirror v0.24.0 exactly)

- The second-quantifier subprocess is **never run in CI** — tests inject a fake quantifier.
- The scientifically load-bearing step — pseudobulk gene collapse — is a **pure, CI-tested**
  function. For single-cell this already exists and shipped in v0.32.0
  (`sc_count_concordance.load_mtx_pseudobulk` + `count_concordance.stats_from_counts`), so
  the collapse is already covered; this slice adds the injectable-quantifier seam + CLI
  wiring on top.

## Caveat to resolve first (in the dig / PRD)

A second single-cell quantifier's own **barcode detection / cell calling** can cause benign
gene-total divergence (chemistry, whitelist, aligner bias — not error). Pseudobulk-summing
across all cells washes much of this out at the gene level, and the shipped contract absorbs
the rest (WARN-capped, uncalibrated band, exit-code untouched, UNVERIFIED below the
shared-gene floor). The dig must:
- confirm the second quantifier is fed the **same reads / barcode whitelist** as the primary,
- decide which quantifier pair is the sane default (e.g. STARsolo ⇄ alevin-fry, keyed off
  what the primary `nf-core/scrnaseq` run used), and how `--index`/whitelist inputs are
  supplied,
- name what "second matrix" the quantifier emits and how it maps into `load_sc_matrix`.

## Shipped precedents to mirror

- **v0.24.0** — RNA-seq kallisto autorun `--concordance-counts-auto`
  (`verification/count_quantifier.py`: `CountQuantifier` seam, pure `kallisto_command` argv
  builder asserted-not-executed, `run_kallisto_quantifier`, `SecondQuantifierError`, pure
  CI-tested `collapse_to_gene`). The closest structural template.
- **v0.4.0** — germline autorun `--concordance-auto` (`verification/second_caller.py`).
- **v0.32.0** — user-supplied single-cell slice `--concordance-sc-counts`
  (`verification/sc_count_concordance.py`: `load_mtx_pseudobulk`, `load_sc_matrix`; reuses
  `count_concordance.stats_from_counts` / `results_from_counts`).

## Guardrails (CLAUDE.md)

- Layer-2 only (run/self-heal/verify/reproduce). Verification depth — on-thesis.
- No raw-read egress: the quantifier runs on the user's compute; only gene-count metrics are
  compared.
- No correctness over-claiming: concordance is corroboration, at most WARN; UNVERIFIED is
  never rendered as PASS.
- No new dependency (stdlib collapse); research-use, never a clinical claim.
- Test-first: every capability lands with its failing test written first.

## Deferred (out of scope for this slice, name in PRD)

- Cell-count and cluster-stability agreement (needs a downstream clustering step Contig
  doesn't run — same blocker as single-cell doublet/mito plausibility).
- FAIL severity until bands are calibrated on real data.
- A dashboard "corroborated by" line for single-cell.
- `.h5ad`/AnnData second-matrix parsing (dependency-gated).
