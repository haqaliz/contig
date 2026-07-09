# PRD — RNA-seq turnkey cross-tool concordance autorun (`--concordance-counts-auto`)

Feature slug: `rnaseq-concordance-autorun` · Type: feat · Owner: aliz
Branch: `feat/rnaseq-concordance-autorun/aliz` · Capability: **C1 (cross-tool concordance
verification), RNA-seq slice — turnkey autorun follow-on**
Status: drafted 2026-07-08 (Phase 3, `contig-begin-fast`)

## Problem Statement

Contig's RNA-seq verdict can already be corroborated by a **second, independent gene-count
matrix** the user supplies (`contig verify --concordance-counts <matrix>`, shipped v0.12.0).
But the user must first *produce* that second matrix themselves — run a whole second
quantifier by hand — which is exactly the "scavenge a second pipeline together" work Contig
exists to remove. Germline variant calling already closed this gap: the user-supplied
`--concordance-vcf` (v0.2.0) was followed one release later by the turnkey
`--concordance-auto` (v0.4.0), which runs a second caller (bcftools) itself. RNA-seq has the
user-supplied half but not the turnkey half.

**Who has the problem:** the Contig RNA-seq ICP — a lone computational biologist or a
wet-lab scientist who can't code — who wants a second-tool corroboration of their
quantification but will not stand up a second quantifier pipeline by hand.

**Evidence it's real:** the germline autorun shipped for exactly this reason and is the
established pattern (`CHANGELOG.md` v0.4.0); the RNA-seq autorun is the explicitly-named,
sequenced-not-blocked deferral in `docs/technical/CAPABILITY_ROADMAP.md` C1 ("auto-running a
second quantifier … mirrors how the germline autorun followed the user-supplied slice one
release later").

## Goals & Success Metrics

- **G1 — Turnkey second-tool corroboration for RNA-seq.** `contig verify
  --concordance-counts-auto --reads <…> --index <…>` runs a second quantifier (kallisto)
  behind an injectable seam and feeds its gene-count matrix into the shipped
  `evaluate_count_concordance`, with no user-produced matrix required.
- **G2 — Honest contract preserved.** At most WARN; never changes the verify exit code;
  never promotes UNVERIFIED→PASS; UNVERIFIED below 10 shared genes; every unrunnable path
  (missing input, missing binary, quantifier failure, non-rnaseq run) prints a skip note and
  emits no checks — never a false pass.
- **G3 — Never runs the tool in CI.** The second quantifier is behind an injectable seam;
  tests exercise the pure argv builder, the honest error paths, and the CLI wiring with an
  injected fake quantifier. No real kallisto/nf-core run in CI.

**Measurable acceptance:**
- A concordant injected matrix → PASS concordance checks; a divergent one → WARN, exit 0.
- Missing `--reads` or `--index`, a quantifier failure, and a non-rnaseq run each → a skip
  note and zero concordance checks, exit unchanged.
- `--concordance-counts-auto` combined with any other concordance flag → exit 1 with a
  "choose one" message.
- Full suite green (`uv run pytest`); no change to any existing verdict/exit behavior.

## User Personas & Scenarios

- **Priya, lone computational biologist.** Ran an nf-core/rnaseq quantification via Contig.
  Wants a sanity check that a different tool agrees before citing the counts. She has a
  prebuilt kallisto index for her organism. Runs `contig verify <run>
  --concordance-counts-auto --reads samples.csv --index idx/` and gets a "corroborated by
  kallisto" WARN/PASS line without assembling a second pipeline.

## Requirements

### Must-have (slice 1)
- **M1 — CLI flag.** Add `--concordance-counts-auto` (bool) to `contig verify`, plus
  `--reads` (FASTQ or sample-sheet path) and `--index` (prebuilt kallisto index). Join the
  existing mutual-exclusion guard so at most one of `--concordance-vcf`,
  `--concordance-auto`, `--concordance-counts`, `--concordance-counts-auto` may be set
  (`cli.py:795-801`, reword the message; add a 4th `elif` dispatch branch at
  `cli.py:811-820`).
- **M2 — Injectable second-quantifier seam.** New `verification/count_quantifier.py`
  mirroring `verification/second_caller.py`:
  - `CountQuantifier = Callable[[reads, index, out_dir], matrix_path]` type.
  - Module-const `_KALLISTO = "kallisto"` (monkeypatch point for the missing-binary test).
  - Pure argv builder `kallisto_command(reads, index, out_dir)` — asserted in tests, never
    executed.
  - Default `run_kallisto_quantifier(reads, index, out_dir) -> gene_matrix_path` that
    validates inputs exist, shells out, raises a named `SecondQuantifierError` on
    missing-binary (`FileNotFoundError`) and nonzero exit; **never run in CI** (docstring
    states this, mirroring `second_caller.py`).
- **M3 — CLI evaluator.** New `_evaluate_run_counts_concordance_auto(record, runs_dir,
  run_id, reads, index, quantifier=None)` mirroring `_evaluate_run_concordance_auto`
  (`cli.py:889-927`): resolve the primary matrix via the existing `_resolve_primary_counts`
  (`cli.py:958-985`, rnaseq-gated skip note + `*salmon.merged.gene_counts*` glob); skip with
  a note when `--reads`/`--index` are missing or absent on disk; run the quantifier in a
  `TemporaryDirectory`; catch `SecondQuantifierError` → skip note; then
  `evaluate_count_concordance(primary, produced_matrix, assay="rnaseq")`.
- **M4 — No verdict-plumbing change.** Reuse the assay-agnostic attach/echo path in
  `verify()` (`cli.py:808-869`); concordance stays WARN-capped and never gates exit.
- **M5 — Tests (test-first).** `tests/verification/test_count_quantifier.py` (argv builder +
  missing-binary / missing-reads / missing-index error paths); `tests/test_cli.py` block
  cloning the germline autorun tests with an injected fake quantifier that writes a
  gene-count matrix (concordant→PASS, divergent→WARN, at-most-WARN exit 0, `--json` includes
  `concordance`, missing-input skip, quantifier-failure skip, non-rnaseq skip,
  mutual-exclusion exit 1).

### Should-have
- **S1 — Echo a "corroborated by kallisto" label** in the concordance echo so the second
  tool is named in the report (germline names its second caller similarly).

### Nice-to-have / explicit follow-ons (NOT this slice)
- Persisted-sample-sheet fallback for `--reads` (default to `parameters["input"]` when it
  still exists) — deferred; slice 1 requires explicit `--reads`.
- `--transcriptome` (build the index in the seam) as an alternative to a prebuilt `--index`.
- Single-cell concordance; a dashboard "corroborated by" line; FAIL severity / band
  calibration (all deferred per `CAPABILITY_ROADMAP.md` C1).

## Technical Considerations

- **Architecture fit.** Pure verify-time / Layer-2 addition. Reuses: the mutual-exclusion
  guard + dispatch (`cli.py`), the `second_caller.py` seam pattern, `_resolve_primary_counts`,
  and the shipped `evaluate_count_concordance` (`count_concordance.py:309`, gated to
  `{"rnaseq"}`, takes two matrix **paths**). No new metric math, no model/persisted-record
  change, no verdict/exit change.
- **Gene-level output (flagged pitfall).** kallisto emits **transcript-level** abundances,
  while the primary is the **gene-level** Salmon merge. The seam's OUTPUT CONTRACT is a
  **gene-level count matrix path**, so `evaluate_count_concordance` compares like with like.
  The transcript→gene collapse lives **entirely inside the never-run-in-CI default impl**
  (`run_kallisto_quantifier`), which will collapse using a transcript→gene map carried in the
  kallisto index directory (the `t2g.txt` convention produced by `kb ref`). Because the
  default impl is never executed in CI and tests inject a fake quantifier that writes a
  gene-level matrix directly, this is a **documented correctness note for the default impl**,
  not a CI-tested path. See Open Questions Q1.
- **Reproducibility / verification impact.** None to the run record or the reproduce
  contract — this is a corroboration computed at `verify` time and only attached/echoed
  (`cli.py:808-869`). No raw-read egress: the quantifier runs on the user's compute; only
  gene-count metrics are compared.
- **Guardrails (CLAUDE.md).** Layer-2 (corroborate a result), no Layer-1 surface, no
  wet-lab/clinical dependency, runs on user compute. Clean.

## Risks & Open Questions

- **R1 — Turnkey-that-isn't (the failure mode from the challenge).** Requiring `--reads` +
  a prebuilt `--index` at verify time is itself friction; if it's as much work as producing a
  matrix, adoption is low. *Mitigation:* the prebuilt-index + explicit-reads contract is the
  minimal honest slice (matches germline); the sheet-fallback and in-seam index build are
  named follow-ons if usage warrants. Accepted with eyes open.
- **R2 — Bounded value.** WARN-only corroboration; no new verdict lever and **no corpus
  fuel** (concordance is not a `FailureClass`). Deepens moat #1 (novel cross-tool verdict)
  only. Accepted (germline v0.4.0 shipped under the same terms).
- **Q1 (open) — gene-level collapse mechanism.** Confirm the `t2g.txt`-in-index-dir
  convention for the default impl's transcript→gene collapse, or decide to require a separate
  `--tx2gene` input. Does not block the CI-tested surface (builder + wiring + skip paths +
  concordance on synthetic gene matrices); resolve in `tech-plan`.
- **Q2 (open) — `--reads` accepts FASTQ vs a sample sheet vs both.** Germline `--bam` was a
  single file. Decide the exact accepted shape (leaning: a sample-sheet path, reusing
  `samplesheet.fastq_paths`, since RNA-seq runs are multi-sample). Resolve in `tech-plan`.

## Out of Scope

- Actually executing kallisto in CI (seam is injected; real tool never run).
- Persisted-sheet `--reads` fallback; in-seam index building from `--transcriptome`.
- Single-cell concordance; dashboard "corroborated by" line; FAIL severity / band
  calibration on real data.
- Any change to the verdict, exit-code logic, run record, or reproduce contract.
- Any Layer-1 (NL → workflow) surface.
