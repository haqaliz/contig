# Understanding — feat / sc-concordance-autorun (Phase 2 deep dig)

Grounded in a full code map of the worktree (path:line cited). Read with `_card/issue.md`.

## What the work is really asking

Make the single-cell concordance axis **turnkey**. Today `contig verify
--concordance-sc-counts <matrix>` (v0.32.0) requires the user to hand Contig a *second*
single-cell count matrix produced by a different tool. Most single-cell users won't have
one. The autorun `--concordance-sc-counts-auto` makes Contig produce that second matrix
itself — run a second, independent single-cell quantifier behind an injectable seam, collapse
its output to per-gene pseudobulk, and feed it into the already-shipped concordance core.

This is the exact analogue of the RNA-seq kallisto autorun `--concordance-counts-auto`
(v0.24.0), which followed the user-supplied `--concordance-counts`.

## The good news: the hard/scientific half already exists

The plumbing this slice reuses, unchanged:

- **Pseudobulk collapse + loader** — `verification/sc_count_concordance.py:61-170`
  (`load_mtx_pseudobulk`, `load_sc_matrix`). Reads a `matrix.mtx` triplet → `{gene_id: float}`
  pseudobulk. Pure stdlib, already CI-tested in v0.32.0.
- **Concordance core** — `verification/count_concordance.py:192-333`
  (`stats_from_counts` / `results_from_counts`, `{gene_id: float}` in, `list[QCResult]` out).
  Spearman + fraction-agreeing WARN-capped at 0.90, informational `gene_overlap`, UNVERIFIED
  below `_MIN_SHARED_GENES = 10`.
- **The whole CLI concordance contract** — `cli.py:750-935` verify command: flags, the
  mutual-exclusion counter (`:841-859`), the dispatch `if/elif` (`:869-886`), the
  "compute-concordance-off-the-critical-path so it can never touch `ok`/exit" guarantee
  (`:866-868`, `:895-896`), skip-note printing (`_echo_concordance`, `:1161-1168`), and the
  `scrnaseq`-gated primary-matrix resolver `_resolve_primary_sc_matrix` (`:1070-1100`,
  prefers `filtered/` over `raw/`).

So the scientifically load-bearing step (pseudobulk collapse) is **already covered** — this
slice is a plumbing slice, exactly as the card promises.

## The new work (small, well-templated)

Mirror `verification/count_quantifier.py` (the kallisto seam) into a new
`verification/sc_count_quantifier.py`:

- `ScCountQuantifier = Callable[[...], str]` — an injectable callable returning the produced
  second-matrix path (a `matrix.mtx` the loader can read).
- A **pure** argv builder (asserted-not-executed in CI) for the chosen tool.
- `SecondScQuantifierError` — one named error folding every unrunnable path (missing binary,
  missing reads/index/whitelist, nonzero exit, missing output).
- A default runner that validates inputs *before* spawn, shells out (**never run in CI**),
  and returns the triplet path.

Then in `cli.py`: one new flag `--concordance-sc-counts-auto` (+ its inputs), one dispatch
branch calling `evaluate_sc_count_concordance(primary, second, assay="scrnaseq")`, and
**extend the mutual-exclusion counter from 5 to 6 flags** (`:841-859` — mechanical, easy to
miss).

Test pattern to copy: `tests/verification/test_count_quantifier.py` (pure argv assert + real
collapse) and `tests/test_cli.py:2061-2270` (inject a fake quantifier via
`monkeypatch.setattr("contig.cli.<runner>", fake_writing_a_triplet)`; a "boom" quantifier
that must NOT be reached on the skip paths).

## The two real decisions (for the requirements interview)

The code map surfaced two genuine gaps that context cannot resolve — these are the interview's
core questions, not implementation details:

1. **Which second single-cell quantifier?** The primary `nf-core/scrnaseq@4.1.0` run defaults
   to **simpleaf / alevin-fry** (`registry.py:60-66` has no `default_params`;
   `single-cell-plausibility/prd.md:22-23,43`). The natural independent second tool is
   **STARsolo**: it emits a native 10x-style `matrix.mtx` triplet (Solo output) that
   `load_sc_matrix` reads directly, and it takes a **STAR genome directory** as its index —
   the same artifact Contig already builds in the shipped STAR-index self-heal. Recommendation:
   default to STARsolo; keep the tool behind the seam so a second tool can be added later.
   *Open:* confirm STARsolo (vs a salmon/alevin second index) as the default.

2. **How are the barcode-whitelist + chemistry supplied?** This is the biggest decision.
   Contig **does not persist** chemistry / whitelist / protocol anywhere — `RunRecord` has
   only a generic `parameters: dict[str, object]` (`models.py:313`); grep for
   `whitelist|chemistry|protocol|barcode|expected_cells` returned zero persisted fields. A
   single-cell second quantifier's cell-calling **depends** on the whitelist + CB/UMI lengths.
   So, like the kallisto autorun requires `--reads`/`--index`, the autorun almost certainly
   needs the user to pass these explicitly. Recommendation: reuse `--reads` (sample sheet) and
   `--index` (STAR genome dir), and add `--whitelist <path>` (required) + `--chemistry`
   defaulting to 10x v3 (CB=16, UMI=12). Every missing/invalid input → an honest skip note and
   zero checks (never a false pass), matching the kallisto autorun.

## Honesty / guardrails held (CLAUDE.md)

- **Layer-2** verification depth — on-thesis, not Layer-1 authoring.
- **No raw-read egress** — the quantifier runs on the user's compute; only gene totals compared.
- **No over-claiming** — concordance stays WARN-capped, never changes the `verify` exit code,
  UNVERIFIED below the shared-gene floor. The divergence-washout claim (pseudobulk summing
  neutralizes benign chemistry/whitelist differences) is an **unproven engineering
  assumption**, which is *why* bands stay WARN-only and FAIL is deferred — flag this in the PRD
  as the calibration open-question, don't paper over it.
- **No new dependency** — collapse is stdlib; the quantifier is an external binary invoked via
  the injected seam, never in CI.
- **Test-first**, no real tool in CI (inject a fake; assert argv without executing).

## Deferred (name in PRD, do not build here)

Cell-count & cluster-stability agreement (needs a downstream clustering step Contig doesn't
run); FAIL severity until bands are calibrated on real data; a dashboard "corroborated by"
line for single-cell; `.h5ad`/AnnData second-matrix parsing (dependency-gated); auto-detecting
the primary run's aligner to key the tool pair (Contig records no aligner today).

## No Layer-1 / scope-drift risk

This is pure verification-harness depth. No workflow authoring, no clinical claim. Clean.
