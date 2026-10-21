# Closing decisions — v1.0.0

Every backlog row now has a terminal state. Nothing here is "still to do": a row
is either **built**, **blocked on evidence only the owner can supply**, **gated by
a trigger the roadmap defined**, or **closed by the decision below**.

## Closed by decision (not built)

| ID | Decision | Why |
|----|----------|-----|
| C1-1 | Won't build | `.h5ad`/AnnData parsing needs a dependency; the project is stdlib-only by contract. Revisit only if the contract changes. |
| C1-2 | Post-1.0 | Cluster-stability agreement needs a downstream clustering step the pipelines don't run. |
| C2-5 | Keep gated | The reference-recompress patch stays `needs_confirmation`. It only writes scratch, but auto-applying a repair is a policy widening with no user asking for it. |
| C2-6 | Keep coupling | `--fasta` without `--gtf` is refused with a clear message; a per-pipeline reference contract is a feature, not a fix. Pinned by test. |
| C2-9 | Post-1.0 | Stall escalation has no precedent to reuse; the watchdog is off by default and uncalibrated. |
| C2-11 | Won't build | Nextflow owns task-level retry; a second retry layer would fight it. |
| C2-22 | Post-1.0 | Pin-conflict repair has no live trigger and no agreed repair shape. |
| C3-2 | Won't build | Doublet rate needs scanpy/scDblFinder — a dependency the contract forbids. |
| C3-4 | Post-1.0 | Multi-sample support touches every plausibility pack's sample model; a real feature cycle, not a follow-on. |
| C5-1 | Post-1.0 | Assembly-signature mismatch has no sample-side contig signal in raw FASTQ; the check cannot be honest yet. |
| C5-3 | Post-1.0 | No reliable machine-readable GTF/annotation version source exists; anything else is a guess. |
| C7-2 | Post-1.0 | Variant prioritization is a new capability, explicitly a deferred follow-on in C7. |
| C8-20 | Blocked | PDF-table extraction needs a real PDF corpus; there is no `.pdf` fixture in the repo. |
| C8-23 | Won't build | `pattern`/notebook locator inference collides with the exactly-one-match rule; needs a design the repo hasn't settled. |
| C8-25 | Post-1.0 | Per-run venv isolation is an environment-model change, not an item. |
| C9-1 | Won't build | Self-heal attempt ordering needs an axis that does not exist; inventing one would be a guess. |
| C9-2 | Won't build | No fifth guard axis exists. `recovery_rate` is deliberately informational in both guards. |

## Gated (the roadmap's own triggers)

C2-1, C2-2, C2-3, C2-4 (no live trigger for build/redirect or CRAM↔BAM),
C2-12 (watchdog on-by-default needs real-run evidence), C8-5 (`occurrence`/`group`
needs a counted experiment over five real repos).

## Blocked on owner evidence

- **Real-run gates (5):** C2-23, C7-3, C8-26, C8-27, C8-28.
- **Band calibration (8):** C1-3, C2-8, C2-13, C3-7, C3-8, C4-2, C6-3, C9-4.
- **Missing upstream artifact/data (8):** C2-20, C3-1, C3-3, C3-6, C3-9, C3-10,
  C7-1, C8-20.

`BLOCKED_RUNBOOK.md` records what to collect for each and what to change once the
evidence exists.

## Declined

C8-2 (plot-hash is impossible under stdlib-only), C8-3 (DOI resolution is out of
scope by the roadmap's own text), C8-7 (regex over binary), C8-11 (non-text
notebook outputs carry no numeric value).

## What "1.0" means

1.0 is the claim set the engine actually makes today: four assays end-to-end
(bulk RNA-seq, germline, somatic, single-cell), self-heal with guards, verdicts
that cannot manufacture a pass, reproduce with signatures, and a dashboard that
renders every check it stores. The closed rows above are **post-1.0 scope**, not
debt: none of them is a known defect, and several would require inventing data or
widening a safety boundary to build.
