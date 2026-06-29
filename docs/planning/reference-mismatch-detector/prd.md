# PRD: reference-mismatch-detector (pre-flight reference-consistency check)

Status: draft for review. Owner: aliz. Branch: `feat/reference-mismatch-detector/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff), `_card/understanding.md`
(Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md` C5. Capability: **C5 slice 2**
(follow-on to the reference-identity **capture** slice shipped v0.6.0).

## Problem Statement

Contig launches nf-core runs against a user-supplied reference (`--fasta` + `--gtf`).
When the FASTA and GTF use **incompatible contig-naming schemes** — the classic
`chr1` (UCSC style) in the FASTA vs `1` (Ensembl style) in the GTF — the pipeline
**runs to "success" but produces an empty or near-empty count matrix**: featureCounts
finds no overlap between aligned reads and annotated features. This is a notorious
silent-failure class (`CAPABILITY_ROADMAP.md:247-251`): the run completes, structural
QC passes (the output file exists and is non-empty as a file), and the researcher
gets a biologically meaningless result with no error.

This is squarely the moat (`CLAUDE.md`): "make every verdict harder to fool." The
reference-identity capture slice (v0.6.0) already records *which* FASTA/GTF a run used;
this slice acts on that same input to **catch the mismatch before compute is spent.**

**Evidence it's real:** `chr`-prefix vs Ensembl naming mismatch is one of the most
common nf-core/rnaseq misconfigurations; it is explicitly the failure class C5 was
scoped to prevent. No incumbent (Galaxy, Terra, Seqera, etc.) pre-flight-checks
reference internal consistency (`FEATURES.md:61-68`).

## Goals & Success Metrics

- **G1 — Catch the disjoint mismatch at pre-flight.** A `contig run` with a FASTA and
  GTF whose contig-name sets are **disjoint** is refused before launch (exit 1) with
  a message naming the exact mismatch (e.g. "FASTA uses `chr1`, GTF uses `1`").
  *Metric:* an integration-style test proves the run never starts (no `launch.json`
  written, `self_heal_run` never called).
- **G2 — Zero false refusals on legitimate references.** A FASTA/GTF pair that shares
  at least one contig name (incl. a GTF that is a strict subset of FASTA contigs —
  partial/scaffold references) launches normally. *Metric:* tests for subset and
  partial-overlap pairs pass through; no real-fixture run regresses.
- **G3 — Honest escape hatch.** `--allow-reference-mismatch` bypasses the refusal
  (still printing the warning) for the rare intentional case. *Metric:* a test shows
  the flag converts the refuse into a proceed.
- **G4 — No regression, no network, no tool execution.** The full suite
  (baseline 847 passed, 1 skipped) stays green; the check is pure local file parsing.

## User Personas & Scenarios

- **A, lone computational biologist:** points Contig at a genome FASTA downloaded from
  UCSC and a GTF from Ensembl; today gets an empty matrix and hours of confused
  debugging. Wants the tool to catch the mismatch in the first second.
- **C, core facility:** runs many references for many PIs; wants a consistent guard so
  a mis-paired reference never silently ships a meaningless result to a non-expert PI.

## Requirements

### Must-have (this slice)

- **R1 — Contig-name extractor.** A function that reads a FASTA and returns its set of
  contig names (the first whitespace-delimited token of each `>` header, `>` stripped),
  and one that reads a GTF and returns its set of contig names (field 0 of each
  non-`#`, tab-split line). Both **gzip-transparent** (`.fa.gz`/`.gtf.gz`), streamed
  (not slurped — references are large), tolerant of blank/garbage lines.
- **R2 — Disjoint-only mismatch rule.** Given the two name sets, report a mismatch
  **only when their intersection is empty** *and* both sets are non-empty. A non-empty
  intersection (incl. GTF ⊆ FASTA) → no mismatch. Either set empty/unparseable →
  **uncomparable = no mismatch** (never a false refuse).
- **R3 — Precise message.** On a mismatch, the message names representative contigs
  from each side and, when detectable, the `chr`-prefix pattern specifically
  (e.g. "FASTA uses `chr`-prefixed names (chr1, chr2, …); GTF does not (1, 2, …)").
- **R4 — Pre-flight gate, refuse + override.** Wire the check into
  `cli.py:_dispatch_run()` immediately after `resolve_reference` populates
  `params["fasta"]`/`["gtf"]` (explicit mode only; iGenomes skipped for free), before
  `launch.json` is written and before `self_heal_run`. On a mismatch and no override:
  print the message to stderr and `raise typer.Exit(code=1)`. With
  `--allow-reference-mismatch`: print the warning and proceed.
- **R5 — Mirror the established pre-flight pattern.** Follow the
  `validate_samplesheet`/`preflight_*` shape: the check core returns `list[str]`
  problems (empty = OK); the CLI decides to exit. Keep the detection logic in a small
  dedicated module, unit-testable without the CLI.
- **R6 — Tests-first, real files via `tmp_path`.** No mocks, no network, no nf-core
  run. Cover: disjoint (refuse), shared/subset (pass), partial overlap (pass),
  gzipped inputs, empty/garbage file (pass = uncomparable), the `--allow-reference-mismatch`
  bypass, and the gate-level behavior (refused run writes no `launch.json`).

### Should-have

- The override flag's help text explains *why* it exists (intentional cross-naming is
  almost always a mistake).

### Nice-to-have (explicitly later, not now)

- Normalizing-suggestion ("strip the `chr` prefix to match") — a hint only, no rewrite.

## Technical Considerations

- **Chokepoint:** `src/contig/cli.py:_dispatch_run()` after cli.py:380. Reference paths
  are absolute and existence-validated there. One insertion covers **CLI and dashboard**
  (the dashboard run-trigger spawns the same `contig run` CLI — `dashboard/lib/runs.ts:511`),
  so **no TypeScript change** is needed.
- **Module:** new `src/contig/reference_check.py` (parsing + rule), keeping `reference.py`
  focused on resolution. Reuse the gzip-open idiom from `concordance.py:_open_text`.
- **Reuse vs ReferenceIdentity:** `ReferenceIdentity` is a *finalize-time* capture
  (`bundle.py:76-109`); the gate runs at pre-flight, so it consumes the same resolved
  FASTA/GTF **paths** from `params`, not the `ReferenceIdentity` object. (The brief's
  "reuse ReferenceIdentity" = reuse the same reference inputs.)
- **Verification honesty (CLAUDE.md):** refuse only on a clear *disjoint* mismatch;
  pass when uncomparable; never fabricate. The override keeps Contig un-paternalistic.
- **Reproducibility impact:** prevents a class of irreproducible-by-meaninglessness
  runs from ever starting; complements the v0.6.0 identity capture.
- **No raw-read egress:** reads only the reference files, locally.

## Risks & Open Questions

- **R-risk-1 — False refusal on an exotic-but-valid reference.** Mitigated by the
  disjoint-only rule (any single shared contig passes) **and** the override flag.
  Residual risk is near-zero (a valid FASTA/GTF pair sharing *no* contig name cannot
  produce results).
- **R-risk-2 — Header parsing edge cases** (FASTA descriptions after the ID, GTF track
  lines / `#!` pragmas, mixed line endings). Mitigated: take the first token only;
  skip `#`-prefixed and blank lines; tolerate and ignore unparseable lines.
- **R-risk-3 — Large-file cost.** Mitigated by streaming line-by-line and only keeping
  the small contig-name set (FASTA: only `>` lines matter; GTF: dedupe field 0). No
  full-file load.
- **Open:** none blocking — all interview decisions resolved.

## Out of Scope (confirmed deferred)

- **Detector corpus + new `reference_mismatch` `FailureClass`.** The corpus models
  run failures (events + logs); a pre-flight refuse has neither, so it doesn't fit the
  shape. Deferred until/unless the C2 reference-mismatch *repair* needs it.
- **Sample-data-vs-reference assembly-signature comparison.** The explicit next C5
  slice; raw FASTQ carries no contig naming and the finished bundle lacks the aligned
  BAM, so there's no reliable sample-side signal at pre-flight.
- **Dashboard / HTML-report UI surface.** The CLI launch gate already protects both
  surfaces.
- **Known-sites / BED-vs-reference consistency and GTF annotation-version resolution.**
- **The C2 reference/build-mismatch *repair*** (this slice only detects/refuses).
- Any clinical claim; any Layer-1 workflow authoring.
