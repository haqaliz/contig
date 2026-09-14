# Understanding — concordance-autorun-inputs

**Status: SHIPPED (Unreleased, 2026-09-13).** Branch:
`feat/concordance-autorun-inputs/aliz`. Shipped in four commits: `83fe3b8`
(feat: derive `--reads` from the run record, integrity-gated), `7dba549` (feat:
GTF-derived t2g map + injectable kallisto index build), `9e133b0` (feat:
`--transcriptome` in-seam kallisto index), and this docs commit
(`docs(changelog): concordance-autorun input derivation + integrity gate (C1)`).

Phase 2 dig note. Grounded in the inline brief (`docs/planning/_card/issue.md`,
itself the contig-next pick) and a two-agent code dig; every citation verified by
reading the file in this worktree (`feat/concordance-autorun-inputs`, base
`7a8c0e3`), not from memory or roadmap prose.

## What the work is really asking

The shipped concordance autorun axes (`contig verify --concordance-counts-auto`
and `--concordance-sc-counts-auto`) require the user to re-supply `--reads` and
`--index` at verify time, even though the run just executed on those very inputs.
The roadmap defers the turnkey follow-on twice: "a persisted-sheet `--reads`
fallback, an in-seam index build from a `--transcriptome`"
(`CAPABILITY_ROADMAP.md:71-73`) and "auto-deriving inputs from the run record"
(`:129-130`). The dig resolves which of those rungs are actually implementable
today, honestly:

**What the bundle persists:** `RunRecord.parameters` (`models.py:337`) carries the
absolutized sample-sheet path as `parameters["input"]` (`cli.py:782`) plus the
resolved `fasta`/`gtf` (explicit-reference mode, `reference.py:41`) or the iGenomes
`genome` key only (`reference.py:27`; iGenomes runs have **no local reference
files** — `bundle.py:163-164`). `reference_identity` (`models.py:346`) mirrors
fasta/gtf + sha256 (`bundle.py:147-180`). `input_checksums` (`models.py:336`)
holds basename→sha256 for the sheet and its FASTQs (`bundle.py:132-144`). The
sheet is **referenced, not copied** into the bundle. `verify` reads only
`run_record.json` (`cli.py:1794`), never `launch.json`.

**The verdict table (which rungs ship):**

| Rung | Verdict | Basis |
|---|---|---|
| `--reads` persisted-sheet fallback (both axes) | **IN SCOPE** | `parameters["input"]`; integrity-checkable against `input_checksums` |
| RNA `--transcriptome` → in-seam kallisto index + GTF-derived `t2g.txt` | **IN SCOPE** | `--transcriptome` is user-supplied by design (`rnaseq-concordance-autorun/prd.md:101,149`); only the build is in-seam; t2g derivable from the run's GTF (explicit runs only); kallisto `index` is a fast build |
| SC `--index` (STAR genomeGenerate at verify time) | **DEFERRED** | unmeasured multi-hour/tens-of-GB build, single-threaded argv (`self-heal-dir-index/prd.md:148,155` debt N1/N2), iGenomes gap, fresh build per verify into a wiped tempdir (`cli.py:2229,2282`); the sc PRD itself recorded auto-derivation "needs new capture wiring first — a separate, larger slice" (`sc-concordance-autorun/prd.md:184-187`) |
| `--whitelist` / `--chemistry` | **STAY USER-SUPPLIED** | persisted nowhere by design (`sc-concordance-autorun/prd.md:154-157`; `CAPABILITY_ROADMAP.md:128-129`) |

## Affected areas (all paths relative to the worktree root)

- `src/contig/cli.py` — the autorun evaluators `_evaluate_run_counts_concordance_auto`
  (`:2192-2237`) and `_evaluate_run_sc_counts_concordance_auto` (`:2240-2296`);
  the flag declarations (`--reads` `:1684-1688`, `--index` `:1689-1697`, plus a
  new `--transcriptome`); the "required/ignored" note sites (`:1752-1765`,
  `:2220-2226`, `:2271-2279`); the six-flag mutual exclusion (`:1767-1792`).
- `src/contig/verification/count_quantifier.py` — `run_kallisto_quantifier`
  (`:139-212`): index must be a **dir** with `t2g.txt` (`:75-82,197-202`); the
  transcript→gene collapse is pure stdlib (`:85-103`). New: pure `t2g_from_gtf`
  parser + injectable `kallisto index` builder seam (never in CI).
- `src/contig/samplesheet.py` — `fastq_paths` (`:172-180`): FASTQs resolve
  relative to the sheet's directory — a derived sheet must still exist at its
  recorded absolute path (rerun precedent: `cli.py:912-914`).
- `src/contig/bundle.py:132-144` — the `input_checksums` computation to mirror
  for the integrity gate (basename → sha256 over the sheet + FASTQs).
- Tests: `tests/test_cli.py` autorun blocks (`:2488` kallisto, `:2726` STARsolo)
  — seam injection via monkeypatched fakes; the missing-input tests assert only
  `"skipping concordance"` and never the exact message, so a derivation fallback
  changes no existing assertion (`:2644-2646`, `:3005-3007`).
  `tests/verification/test_count_quantifier.py` for the pure parts.

## Design decisions (locked in the interview)

1. **`--reads` fallback (both axes):** when the flag is absent, derive from
   `record.parameters["input"]`; then **verify the sheet + FASTQs against
   `input_checksums`** and skip with an honest note on any mismatch/missing file
   (the inputs changed since the run → a comparison would be dishonest). Empty
   `input_checksums` (test-profile/legacy records) → honest skip note ("pass
   `--reads` explicitly"). Explicit `--reads` stays the user's own
   responsibility (unchanged, no gate).
2. **`--transcriptome` (RNA axis):** a new flag, mutually exclusive with
   `--index` for `--concordance-counts-auto` (refusal, "choose one"); ignored
   with a note when the auto flag is absent. In-seam build: injectable
   `kallisto index -i <scratch>/index.idx <transcriptome>` seam (never in CI),
   plus a **pure stdlib GTF→t2g.txt writer** from the run's `parameters["gtf"]`
   — explicit-GTF runs only; iGenomes runs (no local GTF) get an honest skip
   note ("pass `--index`"). The unchanged `run_kallisto_quantifier` then runs
   against the built index dir.
3. **SC `--index` auto-build: DEFERRED** — named blocker above; re-filed in the
   PRD/roadmap, not silently dropped.
4. Order constraints preserved: primary-matrix resolution precedes any input
   handling (`cli.py:2216-2218`, `:2267-2269`); at-most-WARN / exit-untouched /
   zero-checks-on-skip; six-flag mutual exclusion unchanged; no new dependency
   (`pyproject.toml:30-34` — pydantic/typer/cryptography only); no
   model/signature/reproduce-contract change (the derivation reads
   `run_record.json` only — verify-time by construction).

## Open questions for the interview

Resolved: SC STAR rung (deferred), t2g source (explicit-GTF only), integrity
gate (input_checksums). Remaining plan-level questions: the exact t2g.txt
column format the shipped `tx2gene` reader parses (the plan must read
`count_quantifier.py:75-82` before writing the GTF parser), and whether the
FASTQ re-hash pass should be stated as a cost (it is — one read pass over the
same files kallisto is about to read anyway).

## Guardrails check (CLAUDE.md)

Layer 2 (verification turnkey-ness for the shipped C1 axis) ✓. No Layer 1 ✓.
No raw-read egress (everything runs on the user's machine; only checksums are
compared) ✓. No verdict/exit-code/`FailureClass` change ✓. Test-first; the
kallisto index subprocess stays behind an injectable seam, never executed in CI
(parent slices' standing rule) ✓.