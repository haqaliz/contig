# PRD: concordance-autorun-inputs

Status: **SHIPPED (Unreleased, 2026-09-13)** — was "draft for review". Owner: aliz.
Branch: `feat/concordance-autorun-inputs/aliz`. Shipped in four commits: `83fe3b8`
(feat: derive `--reads` from the run record, integrity-gated), `7dba549` (feat:
GTF-derived t2g map + injectable kallisto index build), `9e133b0` (feat:
`--transcriptome` in-seam kallisto index), and this docs commit
(`docs(changelog): concordance-autorun input derivation + integrity gate (C1)`).

Source: inline brief (`docs/planning/_card/issue.md`) picked by `contig-next`;
dig note: `docs/planning/concordance-autorun-inputs/understanding.md`.

---

## Problem statement

The shipped concordance autorun axes (`contig verify --concordance-counts-auto`
and `--concordance-sc-counts-auto`) require the user to re-supply `--reads` and
`--index` at verify time even though the run just executed on those inputs — the
"turnkey-that-isn't" risk the parent PRDs named (`rnaseq-concordance-autorun/prd.md:130-134`).
Both C1 autorun slices deferred the fix in their own words: "a persisted-sheet
`--reads` fallback, an in-seam index build from a `--transcriptome`"
(`CAPABILITY_ROADMAP.md:71-73`) and "auto-deriving inputs from the run record"
(`:129-130`). The run bundle already persists the sample-sheet path
(`RunRecord.parameters["input"]`, `cli.py:782`) and — for explicit-reference
runs — the resolved `fasta`/`gtf` (`bundle.py:147-180`). This slice ships the
rungs that are honestly implementable and defers the one that is not.

## Goals & Success Metrics

Test-first; acceptance is failing tests written before the code. No real
kallisto/STAR/STARsolo in CI (injectable seams, the parent slices' standing rule).

| # | Goal | Success criterion (test) |
|---|------|--------------------------|
| G1 | `--reads` derives from the persisted sheet | `--concordance-counts-auto` / `--concordance-sc-counts-auto` without `--reads`, on a record with `parameters["input"]` + matching `input_checksums` → the quantifier seam is invoked with the derived path; zero user input needed for reads |
| G2 | Derived inputs are integrity-gated | Sheet/FASTQ missing on disk → honest skip note naming the persisted path, zero checks, quantifier never invoked; any sha256 mismatch vs `input_checksums` → honest skip note ("inputs changed since the run"), quantifier never invoked; empty `input_checksums` (test-profile/legacy) → honest skip note ("pass `--reads` explicitly") |
| G3 | `--transcriptome` builds the kallisto index in-seam | `--concordance-counts-auto --transcriptome <fa>` on an explicit-GTF record → injectable `kallisto index` builder called with the expected argv, a kb-compatible `t2g.txt` written from the run's GTF by the pure parser, and the unchanged quantifier invoked against the built index dir; no real kallisto in CI |
| G4 | Ambiguity is refused, not guessed | `--index` + `--transcriptome` together → refusal ("choose one"); `--transcriptome` without `--concordance-counts-auto` → ignored-with-note; six-flag mutual exclusion unchanged |
| G5 | iGenomes gap is honest | `--transcriptome` on a record with no local GTF (`parameters["gtf"]` absent — iGenomes) → honest skip note ("pass `--index`"), no build spawn |
| G6 | Explicit forms byte-identical | `--reads`/`--index` given explicitly → unchanged behavior; every existing autorun test passes unchanged; guards (eval/heal) unmoved; no new dependency; no model/signature/reproduce-contract change |

**Honest framing:** push, not demand-pull — no design partner asked, and the
friction removed is reasoned, not observed. The derived-reads integrity gate
adds a re-hash pass over the sheet + FASTQs (one read pass over files the second
quantifier is about to read anyway); it exists because comparing the run's
matrix against a *changed* input set would be a dishonest concordance. The
kallisto `index` build is fast (minutes for a transcriptome); the STAR
`genomeGenerate` auto-build for single-cell is **deferred** — unmeasured
multi-hour/tens-of-GB single-threaded builds (`self-heal-dir-index/prd.md:148,155`),
an iGenomes-mode gap (no local fasta/gtf persisted, `bundle.py:163-164`), a
fresh build per verify invocation into a wiped tempdir (`cli.py:2229,2282`),
and the sc PRD's own record that auto-derivation "needs new capture wiring
first" (`sc-concordance-autorun/prd.md:184-187`). Revisit trigger: a design
partner running single-cell autoruns repeatedly, or capture wiring for the
run's own STAR index, re-opens it.

## User Personas & Scenarios

The persona is the **lone computational biologist** (persona A, FEATURES.md)
re-verifying a completed run: `contig verify <id> --concordance-counts-auto`
now needs **zero** additional inputs when the run was explicit-referenced and
the sheet still exists — reads come from the record, and an optional
`--transcriptome` replaces the need to have kept a prebuilt kallisto index.
Single-cell keeps requiring `--whitelist` (+ `--chemistry` default `10xv3`),
which Contig cannot know.

## Requirements

**Must-have**
1. `cli.py`: `--reads` fallback in both autorun evaluators — absent flag →
   derive from `record.parameters["input"]`; integrity gate vs
   `input_checksums` (basename→sha256 over sheet + FASTQs, machinery mirrored
   from `bundle.py:132-144`); honest skip notes for missing path, mismatched
   checksum, and empty `input_checksums`.
2. `cli.py`: new `--transcriptome` flag (RNA axis only), mutually exclusive
   with `--index` for `--concordance-counts-auto`; ignored-with-note without
   the auto flag; **path-validated at the CLI** with the parent flags' honest
   "path not found" skip note (a typo'd path must never reach the seam).
3. `verification/count_quantifier.py`: pure `t2g_from_gtf(gtf_path) ->
   dict[transcript_id, gene_id]` (+ gene_name where the GTF carries it) —
   stdlib, CI-tested, kb-ref-compatible t2g.txt format **as parsed by the
   shipped `tx2gene` reader** (verify the exact column contract at plan time,
   `count_quantifier.py:75-82`); malformed/unparseable GTF → honest skip, never
   a fabricated map.
4. `verification/count_quantifier.py`: injectable `kallisto index` builder
   (`Callable[[list[str], Path], int]`-shaped, mirroring `runner.IndexBuilder`),
   argv `kallisto index -i <scratch>/index.idx <transcriptome>`; built dir
   carries the `.idx` + written `t2g.txt` so the **unchanged**
   `run_kallisto_quantifier` accepts it; the build spawn is CI-asserted-not-executed.
5. Tests, RED first: per G1-G6 — seam-injected fake quantifier asserting the
   derived path; boom-fakes asserting never-invoked on every skip path; pure
   t2g parser fixtures (real tiny GTF); refusal and ignored-note cases; all
   existing autorun tests unchanged.

**Should-have**
6. The derived-sheet note distinguishes "derived from the run record" from
   explicit `--reads` in the skip/error wording when the derived path fails.

**Nice-to-have**
7. A `contig show`/report note is **not** needed — no surface change.

## Technical Considerations

- **Reads fallback hooks** immediately before the existing required-input loops
  (`cli.py:2220-2226`, `:2271-2279`); order constraints preserved: primary
  matrix resolution first (`cli.py:2216-2218`, `:2267-2269`), at-most-WARN,
  exit untouched, zero checks on skip.
- **Integrity gate reuses the shipped hashing** (`bundle.py:132-144` shape);
  `input_checksums` keys are basenames, so the derived sheet's FASTQs are
  hashed by the same `fastq_paths` resolution (`samplesheet.py:172-180`).
  **Stated limitation, inherited not fixed:** basename-keyed checksums collide
  for duplicate FASTQ basenames across directories — the same pre-existing
  behavior at run time; a collision can only *fail closed* (mismatch → honest
  skip), never compare against a changed input silently.
- **No new dependency** (`pyproject.toml:30-34`); GTF parsing is attribute
  regex on `gene_id`/`transcript_id`/`gene_name` — stdlib.
- **Verify-time-only by construction:** the derivation reads `run_record.json`,
  never writes it; `rerun`/`resume` replay from `launch.json` and are untouched.
- Dependencies: none new. No model, signature, `FailureClass`, or
  reproduce-contract change. No real kallisto in CI.

## Risks & Open Questions

| # | Risk | Likelihood | Impact | Mitigation / Test |
|---|------|-----------|--------|-------------------|
| R1 | Derived sheet changed since the run (edited/moved FASTQs) | Med | Med (dishonest comparison) | The integrity gate skips on any sha256 mismatch or missing file — pinned by tests |
| R2 | t2g.txt column contract mismatch with the shipped reader | Low | Med | The plan verifies `tx2gene`'s exact parse before writing the writer; a round-trip test asserts the reader accepts the writer's output |
| R3 | A user expects the SC `--index` to also auto-derive | Med | Low | Deferred rung named in the PRD and roadmap; honest skip notes unchanged |
| R4 | Test-profile/legacy records (no `input_checksums`) lose the fallback | Med | Low | Honest skip note directing to explicit `--reads`; explicit forms unchanged |

Open questions: the exact `t2g.txt` column format (plan-level, see R2).

## Out of Scope

- **Single-cell `--index` auto-build (STAR genomeGenerate)** — deferred, with
  the cost/gap blocker named above.
- `--whitelist` / `--chemistry` derivation — persisted nowhere by design
  (`sc-concordance-autorun/prd.md:154-157`).
- A persisted-transcriptome capture channel at run time (new capture wiring —
  the sc PRD's "separate, larger slice").
- Any change to `sc_count_quantifier.py`, `count_concordance.py`, the eval
  guards, the verdict, exit codes, or the reproduce contract.