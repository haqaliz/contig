# Changelog

All notable changes to Contig are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims for
[semantic versioning](https://semver.org/) once it reaches 1.0.

## [0.1.0] - 2026-06-24

The first tagged release: the Layer-2 engine (run, self-heal, verify, reproduce)
plus a local dashboard, feature-complete against the catalog and validated on real
compute. Pre-revenue, validation phase.

### Engine (CLI)

- Run a curated pipeline, self-heal recoverable failures, verify the output, and
  report an honest verdict (PASS / WARN / FAIL / UNVERIFIED): `contig run`, `show`,
  `list`, `plan`.
- Self-heal loop: detect, diagnose, propose typed patches, apply the safe ones, and
  retry, bounded and logged. Risky patches pause for human approval, with ranked
  options on an ambiguous decision (`contig approve`, `--choose`).
- Live observability and control: `contig status`, `watch`, `cancel`, `resume`,
  `rerun`; lifecycle events to `notifications.jsonl` plus a webhook and optional
  SMTP email.
- Verification: metric QC rule packs per assay plus structural and integrity checks
  (outputs present, non-empty, indexed, gzip and BAM integrity); a missing or corrupt
  required output FAILs the verdict.
- Reproducibility: a pinned, portable run record; `contig verify` re-hashes outputs;
  Ed25519 signed records (`contig keygen`); RO-Crate export and a methods paragraph
  (`contig export --rocrate`, `contig methods`); a self-contained HTML report
  (`contig show --html`).
- Cost and planning: `contig cost` for actuals and `contig estimate` for a pre-run
  estimate; resource actuals captured from the trace.
- The failure-corpus flywheel: capture, promote (`contig corpus-promote`), score
  (`contig eval-detector`, with a pluggable detector incl. an optional LLM detector),
  cluster (`contig clusters`), and track coverage (`contig coverage`) and an accuracy
  trend.
- Cross-run verification benchmarking: `contig benchmark` against a designated
  reference.
- Six assays (RNA-seq, single-cell RNA-seq, germline variant calling, methyl-seq,
  16S amplicon, shotgun metagenomics), two workflow engines (Nextflow and Snakemake),
  and three backends (local, AWS Batch, SLURM; local and SLURM live-validated).

### Dashboard

- A Next.js dashboard over the same engine: launch, live progress and the self-heal
  feed, the approval gate, verdict explainability, output-integrity and signature
  badges, compare, the corpus pending-review and the eval flywheel, cost, and the
  benchmark view.
- Auth0 authentication and role-based authorization, per-user run isolation, and team
  workspaces, with a documented local/test bypass.

### Packaging

- Installable as a Python package, a standalone binary per OS, a container image, and
  (where set up) via Homebrew. See the README for install options.

[0.1.0]: https://github.com/haqaliz/contig/releases/tag/v0.1.0
