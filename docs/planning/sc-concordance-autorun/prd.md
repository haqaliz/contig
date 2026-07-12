# PRD: sc-concordance-autorun (turnkey single-cell cross-tool concordance)

Status: draft for review. Owner: aliz. Branch: `feat/sc-concordance-autorun/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff, 2026-07-12),
`_card/understanding.md` (Phase-2 code map). Capability: **C1 — cross-tool concordance
verification**, single-cell autorun follow-on to the user-supplied
`--concordance-sc-counts` slice shipped v0.32.0 (`CAPABILITY_ROADMAP.md:94-109`).

## Problem Statement

The single-cell concordance axis exists but is **not turnkey**. `contig verify
--concordance-sc-counts <matrix>` (v0.32.0) corroborates a `scrnaseq` run's own count matrix
against a *second* matrix — but the user must produce that second matrix themselves, on a
different tool. Most single-cell researchers won't have a second-quantifier matrix on hand,
so the axis rarely fires in practice. Every sibling assay already closed this gap: germline
`--concordance-auto` (v0.4.0) followed `--concordance-vcf`, and RNA-seq
`--concordance-counts-auto` (v0.24.0) followed `--concordance-counts`. Single-cell is the
last assay whose concordance axis still requires a hand-produced second input.

**Cost of the status quo:** a tool-specific single-cell quantification error (wrong chemistry,
bad barcode whitelist, aligner bias) that passes cell-QC and structural checks but skews the
counts goes uncorroborated, because the user has no easy way to run a second tool. **Evidence
it's real:** the v0.32.0 slice explicitly named the autorun as the follow-on where "turnkey
value lands" (`CHANGELOG.md:93-95`). No incumbent issues a cross-tool single-cell concordance
verdict at all.

This is squarely the moat (`CLAUDE.md`): "make every verdict harder to fool," and the
concordance primitive "gets better as models get better at adjudicating *why* two tools
disagree" (`CAPABILITY_ROADMAP.md:122-125`).

## Goals & Success Metrics

- **G1 — Turnkey second matrix.** `contig verify --concordance-sc-counts-auto --reads <sheet>
  --index <STAR genome dir> --whitelist <path>` runs a second, independent single-cell
  quantifier (STARsolo) itself and corroborates the run's own matrix against it — no
  user-supplied second matrix. *Metric:* a CLI test with an **injected fake quantifier** shows
  a concordant pair → PASS checks, a divergent pair → WARN, with the metric + both tool names
  in the message.
- **G2 — Honest contract, identical to every concordance slice.** At most WARN; **never
  changes the `contig verify` exit code**; UNVERIFIED (never a false pass) below the
  10-shared-gene floor. *Metric:* a divergent-pair test asserts exit code 0; a too-few-genes
  test asserts a single `sc_count_concordance` UNVERIFIED.
- **G3 — Every unrunnable path is an honest skip, never a false pass.** Non-`scrnaseq` run,
  missing `--reads`/`--index`/`--whitelist`, quantifier failure, or malformed sample sheet →
  a clear skip note and **zero** checks. *Metric:* a skip-path test injects a "boom" quantifier
  that must never be reached and asserts zero concordance checks emitted.
- **G4 — Pure argv, no tool in CI.** The STARsolo argv builder is a **pure, CI-asserted**
  function; the subprocess is **never run in CI** (tests inject a fake). The scientific
  pseudobulk collapse is already CI-tested (v0.32.0). *Metric:* the argv-builder unit test
  asserts the command without executing STAR.
- **G5 — No regression, no new dependency, no network.** The full suite stays green; no new
  Python dependency (collapse is stdlib; STARsolo is an external binary behind the seam).

## User Personas & Scenarios

- **A, lone computational biologist:** ran a 10x single-cell experiment through Contig
  (`nf-core/scrnaseq`, default alevin-fry). Wants a second opinion on the count matrix but has
  never run STARsolo by hand. Points Contig at the same reads + a STAR genome dir + the 10x
  whitelist, and gets a corroboration line for free.
- **C, core facility:** processes many single-cell runs for non-expert PIs; wants a consistent,
  push-button cross-tool check so a tool-specific quantification artifact is caught before a
  meaningless matrix ships to a PI.

## Requirements

### Must-have (this slice)

- **R1 — A single-cell quantifier seam** — new `src/contig/verification/sc_count_quantifier.py`,
  mirroring `verification/count_quantifier.py`:
  - `ScCountQuantifier` — an injectable `Callable` returning the produced second-matrix path
    (a `matrix.mtx` `load_sc_matrix` can read).
  - A **pure** STARsolo argv builder (asserted-not-executed in CI), e.g.
    `starsolo_command(fastqs, index, whitelist, chemistry, out_dir) -> list[str]` producing
    `STAR --runMode alignReads --soloType CB_UMI_Simple --soloCBwhitelist <wl>
    --soloCBstart/CBlen/UMIstart/UMIlen <from chemistry> --genomeDir <index> --readFilesIn
    <cDNA,CB reads> --outSAMtype None --soloFeatures Gene --outFileNamePrefix <out_dir>/`.
  - **R1a — Pin the STARsolo read order explicitly (the top STARsolo footgun).** STARsolo's
    `--readFilesIn` order is **`cDNA,CB`** (cDNA/R2 first, barcode/R1 second) — the reverse of
    most tools' intuition; getting it wrong silently yields ~zero cells → UNVERIFIED, not a
    WARN. The argv builder must pin the order in code, and the derivation of which sample-sheet
    mate (R1 vs R2) is CB vs cDNA must be a **unit-tested** function, not an implicit assumption.
  - `SecondScQuantifierError` — one named error folding every unrunnable path (missing binary,
    missing/invalid reads/index/whitelist, nonzero exit, missing Solo `matrix.mtx` output);
    never a silent/partial matrix masquerading as a result.
  - A default runner `run_starsolo_quantifier(reads, index, whitelist, chemistry, out_dir) ->
    str` that validates every input **before** spawn, shells out (**never run in CI**), locates
    the Solo `matrix.mtx` triplet under `out_dir`, and returns its path.
- **R2 — Chemistry presets.** A small fixed table mapping `--chemistry` to CB/UMI geometry;
  default **10x v3** (`CB start 1 len 16, UMI start 17 len 12`). At minimum 10x v3; add 10x v2
  if cheap. An unrecognized chemistry → honest skip (never a guessed geometry).
- **R3 — CLI flag + dispatch** in `src/contig/cli.py` `verify`:
  - New `--concordance-sc-counts-auto: bool`, plus `--whitelist: str` and `--chemistry: str`
    (default `10xv3`); **reuse** the existing `--reads` and `--index` flags.
  - New dispatch branch `_evaluate_run_sc_counts_concordance_auto(...)` that, **in this order**:
    (a) resolves the run's own primary matrix via `_resolve_primary_sc_matrix` (assay-gated to
    `scrnaseq`, prefers `filtered/` over `raw/`) — **if the primary is absent, skip note +
    `[]` and do NOT spawn STARsolo** (never run the second tool pointlessly); (b) validates
    `--reads`/`--index`/`--whitelist` present + existing (else skip note, `[]`); (c) selects
    `run_q = quantifier if quantifier is not None else run_starsolo_quantifier` (the injection
    seam); runs it in a `TemporaryDirectory`; catches `SecondScQuantifierError` → skip note +
    `[]`; and (d) feeds the result through `evaluate_sc_count_concordance(primary, second,
    assay="scrnaseq")` (the **shipped** v0.32.0 evaluator — unchanged, so `load_sc_matrix`
    reads STARsolo's own triplet directly).
  - **R3a — Disambiguate the reused `--index` flag.** `--index` means "kallisto index" for
    `--concordance-counts-auto` and "STAR genome dir" for this slice. Mutual exclusion prevents
    a runtime clash, but the help text is ambiguous: generalize `--index`'s help (or convey the
    STAR-dir meaning via `--concordance-sc-counts-auto`'s help) so a user doesn't hand a
    kallisto index to STARsolo.
- **R4 — Extend mutual exclusion from 5 → 6 flags.** Add `--concordance-sc-counts-auto` to the
  counter block at `cli.py:841-859` and to its error message. (Mechanical, easy to miss.)
- **R5 — Honest contract preserved end-to-end** (G2/G3): at most WARN, exit code untouched,
  UNVERIFIED below the 10-shared-gene floor, every unrunnable path a zero-check skip.
- **R6 — Tests-first, no real tool.** Unit tests for the pure argv builder + chemistry presets
  + **the CB/cDNA read-order derivation (R1a)** + error paths
  (`tests/verification/test_sc_count_quantifier.py`, copying `test_count_quantifier.py`). CLI
  tests injecting a fake quantifier that writes a synthetic `.mtx` triplet (`tests/test_cli.py`,
  copying the kallisto-autorun tests at `:2061-2270`): concordant PASS, divergent WARN,
  at-most-WARN exit 0, JSON payload, **primary-matrix-absent skip (STARsolo not spawned)**,
  missing-input skip with a "boom" quantifier, `SecondScQuantifierError` skip, non-`scrnaseq`
  skip, and the 6-flag mutual-exclusion.

### Should-have

- The new flags' help text states the second tool (STARsolo) and that it runs on the user's
  compute (no raw-read egress).
- 10x v2 chemistry preset alongside v3 if it costs little.

### Nice-to-have (explicitly later, not now)

- Auto-deriving reads/index/whitelist/chemistry from the primary run record (needs new capture
  wiring — see Out of Scope).

## Technical Considerations

- **Chokepoint:** `src/contig/cli.py` `verify` (`:750-935`). The dispatch `if/elif`
  (`:869-886`) and the mutual-exclusion counter (`:841-859`) are the only edits to existing
  control flow; everything else is additive.
- **Zero change to the scientific core.** `evaluate_sc_count_concordance` /
  `load_sc_matrix` / `load_mtx_pseudobulk` (`sc_count_concordance.py`) and
  `stats_from_counts` / `results_from_counts` (`count_concordance.py`) are reused **unchanged**.
  STARsolo's native `Solo.out/**/matrix.mtx` triplet is exactly what `load_sc_matrix` already
  reads, so the second matrix maps in with no new loader. This is why the slice is "plumbing":
  the load-bearing pseudobulk collapse is already shipped and CI-tested.
- **Seam shape** copies `count_quantifier.py` (kallisto) and `second_caller.py` (bcftools): a
  pure argv builder + a validate-before-spawn runner + one named error, injected by
  `monkeypatch.setattr("contig.cli.run_starsolo_quantifier", fake)` in tests; the subprocess
  success path is intentionally not exercised in CI.
- **Reproducibility/verification impact:** additive to the verdict only — **no** new
  `FailureClass`, model, persisted `RunRecord` field, dependency, or reproduce-contract change;
  no exit-code change. Corroboration data (single-cell agreement distributions) begins accruing
  into the eval corpus (moat #2).
- **No raw-read egress:** STARsolo runs on the user's compute; only per-gene pseudobulk totals
  are compared.
- **Whitelist/chemistry are user-supplied** because Contig persists no chemistry/whitelist/
  protocol today (`models.py:313`, `RunRecord.parameters` is a generic dict; grep for
  `whitelist|chemistry|protocol|barcode` → zero persisted fields). Mirrors how the kallisto
  autorun requires `--reads`/`--index`.

## Risks & Open Questions

- **R-risk-1 — Benign cross-tool divergence (the load-bearing honesty item).** STARsolo's own
  barcode detection / cell calling differs from the primary aligner's, so gene totals can
  diverge for legitimate (non-error) reasons. Mitigation: pseudobulk-summing across all cells
  washes much of this out at the gene level, and the contract absorbs the rest — **WARN-capped,
  uncalibrated band, exit code untouched, UNVERIFIED below the floor**. This washout is an
  **unproven engineering assumption**, which is exactly why bands stay WARN-only and FAIL is
  deferred. Not papered over: it is *the* reason for the WARN-only ceiling.
- **R-risk-2 — Chemistry mismatch.** If the user passes the wrong `--chemistry`, STARsolo calls
  few/no cells → few shared genes → honest UNVERIFIED (never a false pass), not a wrong WARN.
- **R-risk-3 — STARsolo argv drift across STAR versions.** Mitigated by keeping the argv builder
  pure + unit-asserted and the tool behind the injectable seam; no version pin claimed.
- **R-risk-4 — A WARN users learn to ignore (the greenlight question).** Because calibration is
  deferred, an early single-cell WARN can't yet distinguish a genuine quantification bug from
  benign cell-calling divergence. Mitigation stance: this is *why* the axis is WARN-only and
  never touches the exit code — a WARN is a "look here," not a verdict. The path off this risk
  is the eval corpus: single-cell agreement distributions accrue per run (moat #2), and once a
  band is calibrated on real pairs, FAIL severity + a sharper message follow (deferred here).
  The alternative — shipping no check — forfeits that corpus data entirely, which is the worse
  trade for a WARN-capped, exit-code-safe signal.
- **Open (non-blocking):** whether to add 10x v2 now or defer (cost-dependent); whether a
  future slice keys the second tool off the primary run's recorded aligner (Contig records no
  aligner today — out of scope here).

## Out of Scope (confirmed deferred)

- **Auto-deriving inputs from the run record.** Contig persists no chemistry/whitelist/aligner;
  auto-derivation needs new capture wiring first — a separate, larger slice.
- **Cell-count and cluster-stability agreement.** Needs a downstream clustering step Contig
  doesn't run (same blocker as single-cell doublet/mito plausibility).
- **FAIL severity + band calibration on real data.** No real single-cell pair available today;
  bands stay WARN-only until calibrated.
- **A dashboard / HTML "corroborated by" line for single-cell.** Deferred across all C1 slices.
- **`.h5ad`/AnnData second-matrix parsing.** Dependency-gated (`anndata`/`h5py`).
- **An explicit divergence-annotation note in the concordance output.** Considered; deferred to
  keep the surface identical to the shipped concordance slices (WARN semantics already convey
  corroboration-not-truth).
- Any clinical claim; any Layer-1 workflow authoring.
