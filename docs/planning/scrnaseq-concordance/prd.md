# PRD: scrnaseq-concordance (single-cell cross-tool count concordance)

Status: draft for review. Owner: aliz. Branch: `feat/scrnaseq-concordance/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff), `_card/understanding.md`
(Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md` C1. Capability: **C1, single-cell
slice** — the last assay without a concordance axis.

## Problem Statement

Contig's verdict gains trust from **cross-tool concordance**: run a second, independent
tool on the same data and treat agreement as corroboration. This primitive already ships
for germline (`--concordance-vcf`/`-auto`), bulk RNA-seq (`--concordance-counts` +
kallisto `-auto`), somatic (auto Mutect2-vs-Strelka2), and annotation (VEP-vs-SnpEff).
**Single-cell RNA-seq (`scrnaseq`) is the only wired assay with no concordance axis** — it
is named as deferred in every C1 list (`CAPABILITY_ROADMAP.md:58,73,117`).

A single-cell run today is verified only by cell-QC plausibility (v0.21.0 — recovered
cells, median genes/cell, fraction reads in cells) and structural presence. Nothing
corroborates the **quantification itself**: whether a *second* quantifier, run on the same
reads, would produce a comparable gene-expression profile. Quantifier-specific error
(mis-set chemistry, wrong barcode whitelist, an aligner bug) can pass cell-QC and yield a
biologically skewed matrix with no signal. Concordance is the axis that catches it.

**Evidence it's real:** the four shipped concordance slices establish the pattern and its
value; the roadmap explicitly scopes single-cell as the remaining slice. No incumbent
(Galaxy, Terra, Seqera, DNAnexus, Latch, Basepair) issues any cross-tool correctness
verdict (`FEATURES.md:61-74`) — this deepens the moat's most defensible primitive.

## Goals & Success Metrics

- **G1 — A single-cell run gains a concordance axis.** `contig verify <id>
  --concordance-sc-counts <second>` corroborates the run's own cell×gene matrix against a
  user-supplied second matrix and emits WARN-capped `kind="concordance"` QCResults.
  *Metric:* an integration test where a concordant pair yields `spearman_concordance` PASS
  with the metric reported, and a divergent pair yields WARN naming the exact value.
- **G2 — Honest contract, identical to every shipped concordance slice.** At most WARN,
  **never changes the `verify` exit code**, and `unverified` (never a false pass) below the
  shared-gene floor. *Metric:* a test proves a divergent pair exits 0; a too-few-shared-genes
  pair yields UNVERIFIED with `value=None`, not PASS.
- **G3 — No new dependency, no raw-read egress, no real tool in CI.** The `.mtx` reader is
  pure-stdlib (matching the `count_concordance.py` "No scipy/numpy" contract). Only gene
  totals are compared, locally. *Metric:* the full suite stays green with no import of
  `scipy`/`numpy`/`anndata`/`h5py`; every test uses synthetic `tmp_path` fixtures.
- **G4 — No regression.** The existing suite (concordance, verify CLI, scrnaseq metrics)
  stays green; the four other concordance flags are unaffected.

## User Personas & Scenarios

- **A, lone computational biologist:** ran an `nf-core/scrnaseq` analysis, also has a
  matrix from a second quantifier (e.g. a STARsolo or Cell Ranger run) and wants a
  one-command sanity check that the two quantifications agree before trusting the counts.
- **C, core facility:** processes single-cell libraries for many PIs and wants a consistent
  corroboration signal attached to the verdict a non-expert PI receives.

*Acknowledged demand risk (see Risks):* many single-cell users will **not** have a second
matrix on hand; immediate turnkey value waits for the deferred autorun follow-on. This
slice establishes the axis, the parser, and the contract that the autorun will reuse.

## Requirements

### Must-have (this slice)

- **R1 — Stdlib MatrixMarket triplet loader → per-gene pseudobulk.** A new pure function that
  reads a `matrix.mtx`(.gz) plus its sibling `features.tsv`(.gz) and `barcodes.tsv`(.gz),
  and returns `{gene_id: float}` where each value is the **sum of that gene's counts across
  all cells** (pseudobulk collapse). Gene id = column 1 of `features.tsv` (Ensembl id;
  fall back to the sole column if only one). MatrixMarket is **gene×cell or cell×gene** —
  detect orientation from the header dimension line against the `features`/`barcodes`
  lengths; refuse ambiguity honestly (see R6). Gzip-transparent, streamed (matrices are
  large), tolerant of the `%%MatrixMarket` banner and `%` comment lines.
- **R2 — Extension-sniffed second-matrix input.** The user-supplied second matrix is a
  `matrix.mtx`(.gz) path (siblings auto-resolved from the same directory) **or** a dense
  pre-collapsed gene TSV. Route by extension: `*.mtx`/`*.mtx.gz` → the R1 loader;
  otherwise → the existing `parse_count_matrix` (`count_concordance.py:80`). Both yield
  `{gene_id: float}` fed to the unchanged core.
- **R3 — Reuse the concordance core unchanged.** Feed both `{gene_id: float}` dicts to the
  shipped `count_concordance()` / `concordance_results()` core
  (`count_concordance.py:192-306`): per-gene **Spearman** (`spearman_concordance`, WARN
  < 0.90), **fraction-agreeing** within 10% (`fraction_agreeing`, WARN < 0.90), and
  informational **`gene_overlap`** (always PASS). Shared-gene floor `_MIN_SHARED_GENES=10`
  drives UNVERIFIED. Do **not** modify the core's math or the RNA-seq path.
- **R4 — New `scrnaseq` entry point + assay gate.** A new `evaluate_sc_count_concordance`
  (not an added string in `_COUNT_CONCORDANCE_ASSAYS`, because `evaluate_count_concordance`
  hardwires the dense `parse_count_matrix` that must **not** be used for the sparse primary).
  It parses the primary via the R1 loader, the second via R2 sniff, gates to
  `assay == "scrnaseq"`, and returns the core's results (or `[]` with a printed skip note).
- **R5 — `verify` CLI wiring.** Add `--concordance-sc-counts <path>` to the `verify` command
  (`cli.py:746-791`), add it to the mutual-exclusion tuple (`cli.py:823`) so it is exclusive
  with the other four concordance flags, add an `elif` branch (`cli.py:~853`) calling a new
  `_evaluate_run_sc_counts_concordance` + `_resolve_primary_sc_matrix` pair modeled on
  `cli.py:993-1036`. The primary matrix is located by `results_dir.rglob("*matrix.mtx*")`,
  assay-gated to `scrnaseq` via `assay_for_pipeline(record.pipeline)`. Results are injected
  into `result["concordance"]` and echoed by `_echo_concordance`; **exit code untouched**.
- **R6 — Every uncomputable path is an honest skip/UNVERIFIED, never a false pass.**
  - Non-`scrnaseq` run → printed skip note, `[]` (mirrors `_resolve_primary_counts`).
  - No `*matrix.mtx*` under the run (e.g. an `.h5ad`-only simpleaf run) → printed skip note,
    `[]`. (`.h5ad` parsing is out of scope — R-oos.)
  - Missing/unreadable sibling `features.tsv`/`barcodes.tsv`, malformed header, or an
    orientation that can't be disambiguated → skip note, `[]` (or an explicit UNVERIFIED for
    a located-but-unparseable second matrix, mirroring the scrnaseq gate's
    located-but-empty → UNVERIFIED convention).
  - Fewer than 10 shared genes → the core's UNVERIFIED (`value=None`), never PASS.
- **R7 — Tests-first, synthetic fixtures, no real tool.** Cover: the `.mtx` loader
  (orientation both ways, gzip, pseudobulk sum, comment/banner skip, missing sibling,
  malformed); the sniff router (`.mtx` vs `.tsv`); a concordant pair (Spearman ~1, PASS), a
  divergent pair (WARN, exit 0), a too-few-shared-genes pair (UNVERIFIED); the CLI gate
  (non-scrnaseq skip, mutual-exclusion error, `result["concordance"]` in `--json`). No
  `nf-core/scrnaseq`, STARsolo, or Cell Ranger execution in CI.

### Should-have

- The flag's help text names the accepted formats (`.mtx`(.gz) triplet or dense gene TSV)
  and states the corroboration-only, at-most-WARN semantics.

### Nice-to-have (explicitly later, not now)

- A one-line "corroborated by a second quantifier" surface on the verdict card / dashboard
  (deferred for every concordance slice; a separate surfacing slice).

## Technical Considerations

- **Chokepoints:** `src/contig/cli.py` `verify` (flag, exclusion, branch, resolver);
  a new `src/contig/verification/sc_count_concordance.py` (the `.mtx` loader + the
  `evaluate_sc_count_concordance` entry point) importing the reusable core from
  `count_concordance.py`. Keeping the new parser in its own module preserves
  `count_concordance.py`'s dense-TSV focus and its stdlib purity.
- **Reuse, don't fork:** the Spearman/rank/fraction-agreeing/floor logic and the QCResult
  builders (`count_concordance.py:115-306`) are consumed unchanged — the one scientifically
  load-bearing addition is the pseudobulk collapse, which is CI-tested for real.
- **Reproducibility/verification impact:** additive to the verdict only — no new
  `FailureClass`, model, persisted record, or dependency; no exit-code change. The
  reproduce contract is untouched (this is a `verify`-time flag, like `--concordance-counts`,
  not a run-time parameter baked into `launch.json`).
- **No raw-read egress:** the loader reads count matrices already on the user's compute and
  compares only per-gene totals.
- **Guardrail (CLAUDE.md):** Layer-2 verification depth; corroboration, not ground truth;
  at most WARN; UNVERIFIED never rendered as PASS. Research-use only.

## Data Model / Artifact Contract

- No change to `RunRecord`, `LaunchManifest`, or the bundle. The new QCResults use the
  existing `QCResult` model with `kind="concordance"` (`models.py:64,67-75`).
- MatrixMarket triplet contract (input): `matrix.mtx`(.gz) coordinate format; `features.tsv`
  (col 1 = gene id, row order = matrix gene axis); `barcodes.tsv` (row order = matrix cell
  axis). The loader derives gene ids from `features.tsv`; barcodes are used only to confirm
  the cell-axis length for orientation detection.

## Risks & Open Questions

- **R-risk-1 — Adoption: no second matrix on hand.** Many single-cell users won't have a
  second quantifier's output. *Mitigation:* framed as the axis-establishing slice; the
  autorun follow-on (a `--concordance-sc-counts-auto`, mirroring kallisto v0.24.0) is the
  turnkey delivery and reuses this parser + core. Documented, not hidden.
- **R-risk-2 — MatrixMarket orientation ambiguity.** A square-ish matrix where genes ≈ cells
  could be mis-transposed. *Mitigation:* orientation is decided by matching the header
  dimensions against the `features`/`barcodes` lengths, not by guessing; a genuine tie →
  honest skip/UNVERIFIED, never an arbitrary transpose.
- **R-risk-3 — Feature id vs gene symbol mismatch across tools.** Tool A keys genes by
  Ensembl id, tool B by symbol → low `gene_overlap`. *Mitigation:* `gene_overlap` is
  informational (always PASS) precisely for this; the shared-gene floor sends a genuinely
  non-overlapping pair to UNVERIFIED, never a false WARN/PASS. (Symbol↔id normalization is
  out of scope, mirroring the annotation slice's minimal-normalization stance.)
- **Open:** none blocking — the three product decisions (input shape, `.h5ad` deferral,
  metric scope) were resolved in the interview.

## Out of Scope (confirmed deferred)

- **`.h5ad` / AnnData parsing** (R-oos). Would add an `anndata`/`h5py` dependency, breaking
  the stdlib-only contract; an `.h5ad`-only run degrades to an honest skip. Deferred until a
  stdlib-safe reader or an accepted dependency exists.
- **Autorun second quantifier** (`--concordance-sc-counts-auto`). A second single-cell
  quantifier's barcode/cell-calling has no clean CI story; the turnkey follow-on, deferred.
- **Cell-count and cluster-stability agreement** (`CAPABILITY_ROADMAP.md:117`). Cluster
  stability needs a downstream clustering step Contig doesn't run (same blocker as
  single-cell doublet/mito plausibility); cell-count agreement depends on each tool's
  cell-calling. Deferred.
- **FAIL severity.** Bands stay WARN-capped until calibrated on real data (consistent with
  every concordance slice).
- **Verdict-card / dashboard "corroborated by" surface.** A separate surfacing slice.
- Any clinical claim; any Layer-1 workflow authoring.
