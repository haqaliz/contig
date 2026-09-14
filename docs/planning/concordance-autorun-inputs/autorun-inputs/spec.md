# Spec: concordance-autorun-inputs / autorun-inputs

**Status: SHIPPED (Unreleased, 2026-09-13).** Branch:
`feat/concordance-autorun-inputs/aliz`. Shipped in four commits: `83fe3b8`
(feat: derive `--reads` from the run record, integrity-gated), `7dba549` (feat:
GTF-derived t2g map + injectable kallisto index build), `9e133b0` (feat:
`--transcriptome` in-seam kallisto index), and this docs commit
(`docs(changelog): concordance-autorun input derivation + integrity gate (C1)`).

Single aspect for the PRD (`docs/planning/concordance-autorun-inputs/prd.md`).
Both rungs land in the same CLI evaluator + test file, so one aspect with
sequential phases (the repo's one-slice-one-aspect pattern).

## Problem slice

Remove the "turnkey-that-isn't" from the shipped concordance autorun axes:
derive `--reads` from the run's persisted sample-sheet path (integrity-gated
against `input_checksums`), and let `--transcriptome` replace a prebuilt
kallisto `--index` via an in-seam index build with a GTF-derived `t2g.txt`.

## In scope

1. `cli.py` — `--reads` fallback (both autorun evaluators) + integrity gate +
   new `--transcriptome` flag (RNA axis) + refusals/notes.
2. `verification/count_quantifier.py` — pure `t2g_from_gtf` + injectable
   `kallisto index` builder seam; the built index dir feeds the unchanged
   `run_kallisto_quantifier`.
3. Tests: G1-G6 (see PRD) — seam-injected fakes, boom-fakes, real tiny GTF
   fixtures, refusal cases; all existing autorun tests unchanged.
4. Changelog + `CAPABILITY_ROADMAP.md` (the two "still deferred" sentences
   become the shipped record; the SC `--index` rung is re-filed as deferred
   with its blocker named).

## Out of scope

SC `--index` auto-build (STAR genomeGenerate); whitelist/chemistry derivation;
run-time transcriptome capture wiring; `sc_count_quantifier.py`,
`count_concordance.py`, verdicts, exit codes, eval guards, reproduce contract,
new dependencies.

## Acceptance criteria (test-first, no real kallisto in CI)

- AC1 Derived reads (RNA): record with `parameters["input"]` + matching
  `input_checksums` → fake quantifier receives the derived sheet path.
- AC2 Derived reads (SC): same for `--concordance-sc-counts-auto`.
- AC3 Integrity gate: missing sheet file → honest skip, quantifier never
  invoked; sha256 mismatch → honest skip ("inputs changed since the run");
  empty `input_checksums` → honest skip ("pass `--reads` explicitly").
- AC4 Transcriptome build: explicit-GTF record + `--transcriptome` → injected
  builder gets `kallisto index -i <idx> <fa>`, `t2g.txt` written from the GTF,
  quantifier invoked with the built dir; a round-trip test proves the shipped
  `tx2gene` reader accepts the writer's output.
- AC5 Refusals: `--index`+`--transcriptome` → "choose one", exit 1;
  `--transcriptome` without the auto flag → ignored-with-note.
- AC6 iGenomes gap: no `parameters["gtf"]` + `--transcriptome` → honest skip
  ("pass `--index`"), no build spawn.
- AC7 Regression: explicit `--reads`/`--index` byte-identical; all existing
  autorun tests green; eval-guard/heal-guard baselines unmoved (verified, not
  asserted); full suite green.

## Dependencies and sequencing

1. Reads fallback + integrity gate (AC1-AC3, AC7) — self-contained.
2. `t2g_from_gtf` + `kallisto index` seam + `--transcriptome` wiring
   (AC4-AC6) — depends on 1 only for the shared evaluator touch.
3. Changelog + roadmap corrections — last; guard re-verification gate.

## Open questions / risks

- The exact `t2g.txt` column format the shipped `tx2gene` reader parses
  (`count_quantifier.py:75-82`) must be read before writing the GTF parser —
  the round-trip test (AC4) pins it either way.
- The FASTQ re-hash pass is a stated cost (one read pass over files the second
  quantifier reads anyway).
- If the GTF carries no `gene_name` attribute, t2g.txt must still be
  kb-compatible (transcript+gene columns only) — never a fabricated name.