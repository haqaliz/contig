# Understanding note — rnaseq-concordance-autorun (Phase 2 dig)

Date: 2026-07-08 · Branch: `feat/rnaseq-concordance-autorun/aliz`

## What the work is really asking

Make RNA-seq cross-tool concordance **turnkey**: `contig verify <run>
--concordance-counts-auto …` runs a second, independent quantifier behind an injectable
seam to produce a second gene-count matrix, then feeds it into the shipped
`evaluate_count_concordance` (v0.12.0). It follows RNA-seq `--concordance-counts` (v0.12.0)
exactly as germline `--concordance-auto` (v0.4.0) followed germline `--concordance-vcf`
(v0.2.0). **No blocker** — proven template, concordance math already ships, second tool
never runs in CI (injected seam).

## The template to copy (germline autorun, all code-verified)

- **CLI flag surface + 3-way mutual-exclusion guard** — `cli.py:747-771` (options),
  `cli.py:795-801` (guard: `sum(bool(x) for x in (...)) > 1` → exit 1), `cli.py:811-820`
  (dispatch). New flag joins the guard (→ 4-way) and adds an `elif` dispatch branch.
- **Injectable seam** — `verification/second_caller.py`: `VariantCaller =
  Callable[[bam, ref, out_dir], vcf_path]`, module-const binary name (monkeypatch point),
  pure argv builder `bcftools_command` (asserted in tests, never run), default
  `run_bcftools_caller` that validates inputs then raises `SecondCallerError` on
  missing-binary/nonzero-exit. Injected in CLI at `cli.py:889-927`
  (`_evaluate_run_concordance_auto`), monkeypatched in tests via
  `contig.cli.run_bcftools_caller`.
- **Skip-note / never-false-pass** — every unrunnable path echoes a skip note and returns
  `[]` (no checks), never raises, never changes exit code: wrong assay
  (`cli.py:930-944`), missing primary (`949-954`), missing `--bam`/`--ref`
  (`912-918`), `SecondCallerError` (`922-926`).
- **Verdict plumbing is already assay-agnostic** — `verify()` computes concordance up front
  and only *attaches/echoes* it; exit is decided solely by checksum drift + signature
  (`cli.py:808-869`). `evaluate_count_concordance` already returns `kind="concordance"`
  WARN-capped QCResults. **No verdict changes needed.**
- **Tests** — seam unit tests `tests/verification/test_second_caller.py` (argv builder + 3
  error paths); CLI integration `tests/test_cli.py:1611+` (fake caller factory writing a
  recorded output, mutual-exclusion `test_...flags_mutually_exclusive` 1590-1608).

## Shipped comparison machinery to reuse (no new math)

- `evaluate_count_concordance(primary, second, assay)` — `count_concordance.py:309`,
  assay-gated to `{"rnaseq"}`; takes **two matrix file paths**. Emits `spearman_concordance`
  + `fraction_agreeing` (WARN-capped, `<0.90`) + `gene_overlap` (informational/PASS);
  UNVERIFIED below `_MIN_SHARED_GENES=10`. Hand-rolled Spearman + tolerant gzip parser.
- Primary matrix locator `_resolve_primary_counts` (`cli.py:958-985`) globs
  `*salmon.merged.gene_counts*` (`count_concordance.py:49-51`); reuse as-is.

## The one real design decision — RESOLVED: inputs are user-supplied

A second quantifier (kallisto, or Salmon against a freshly built transcriptome index) needs
**reads (FASTQ) + a transcriptome/index**. These are **not reliably in the run record**:
- `verify` loads only `run_record.json` (`cli.py:803` → `workspace.load_run`); `launch.json`
  is NOT read by verify.
- `RunRecord` persists `parameters["input"]` (sheet path), `fasta`/`gtf`/`genome`, and
  **basename→sha256** checksums — FASTQ *paths* are discarded (`bundle.py:61-73`); a
  transcriptome/index is **never** persisted; and iGenomes (`--genome KEY`) runs persist no
  local FASTA/GTF at all.

**Decision (mirrors germline exactly):** the autorun takes its inputs from **CLI options**,
not the record — just as `--concordance-auto` took `--bam`/`--ref` from the CLI. Proposed:
- `--concordance-counts-auto` (bool), mutually exclusive with the other 3 concordance flags.
- `--reads` (FASTQ or a sample sheet) — MAY default to the persisted sheet
  (`parameters["input"]`) when it still exists, as a *convenience fallback only*, not the
  contract.
- `--transcriptome` (transcript FASTA) or `--index` (prebuilt index) — **must be
  user-supplied** (direct analog of germline `--ref`; nothing in the record to derive it
  from, and igenomes runs have no local reference).

**Seam:** new `verification/count_quantifier.py` mirroring `second_caller.py`:
`CountQuantifier = Callable[[reads, transcriptome_or_index, out_dir], matrix_path]`, pure
argv builder (kallisto/salmon) asserted in tests, default impl validates inputs + raises a
named `QuantifierError`, **never executed in CI**. New
`_evaluate_run_counts_concordance_auto(...)` mirrors `_evaluate_run_concordance_auto`,
resolves primary via `_resolve_primary_counts`, skip-with-note on missing inputs / quantifier
error, runs the quantifier into a `TemporaryDirectory`, then
`evaluate_count_concordance(primary, produced_matrix, assay="rnaseq")`.

## Guardrail check (CLAUDE.md)

Layer-2 (verify/corroborate), no wet-lab/clinical dependency, no Layer-1 surface, runs on
user compute (no raw-read egress — the quantifier runs locally, only metrics compared).
Clean.

## Honest caveats (carry into the PRD)

- WARN-only corroboration; never changes the exit code. Turnkey convenience, not a new
  verdict lever. Bounded marginal value — same as germline v0.4.0, which shipped anyway.
- Proves the **wiring**, not a real second-tool run (seam injected in tests; quantifier
  never run in CI).
- **No corpus fuel** (concordance is not a `FailureClass`) — deepens moat #1 only.

## Open questions for the interview (Phase 3)

1. Second quantifier choice: **kallisto** (cleaner independence — pseudo-alignment, distinct
   algorithm from Salmon) vs Salmon-in-mapping-mode. Leaning kallisto for independence.
2. `--reads`/`--transcriptome`/`--index` exact flag shape, and whether to include the
   persisted-sheet convenience fallback in slice 1 or defer it.
3. Whether to gzip-collapse kallisto transcript-level abundances to gene level inside the
   seam, or require a gene-level second matrix (the primary is gene-level Salmon merge).
