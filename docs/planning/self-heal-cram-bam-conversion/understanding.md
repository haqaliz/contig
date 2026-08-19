# Understanding — self-heal-cram-bam-conversion (C2 input-format class, second half)

Deep-dig note. Two parallel agents mapped (a) the C2 machinery the slice must reuse and
(b) the reachable-trigger question. All citations verified in the worktree
(`feat/self-heal-cram-bam-conversion`, base b8b2092).

## What the work is really asking

The bgzip-reference slice (Unreleased) shipped the input-format-conversion class's first
half: a plain-gzip reference FASTA is detected (`reference_not_bgzf`), stream-decompressed
into scratch, params redirected, run retried. It explicitly deferred the class's second
half: **CRAM↔BAM conversion** (`docs/planning/self-heal-bgzip-reference/prd.md:187`,
`CAPABILITY_ROADMAP.md` C2). This slice is that second half — *as scoped by the reachability
finding below*: **detector + corpus only**, no convert-and-retry machinery.

## The central finding: no reachable live trigger (the bwa-mem2 verdict)

A Contig-launched run **cannot** reach a CRAM/BAM format failure today:

- Contig's samplesheet models are **FASTQ-only** — `SampleRow {sample, fastq_1, fastq_2,
  strandedness}` (`samplesheet.py:11-15`) and `SarekSampleRow {patient, sample, status, lane,
  fastq_1, fastq_2}` (`samplesheet.py:18-32`). No `bam`/`cram` column anywhere; a sarek
  BAM/CRAM sheet is refused at pre-flight as "missing required column: 'fastq_1'"
  (`cli.py:589-593`).
- The launch argv is mechanically `--key value` over params (`runner.py:1149-1181`);
  `--opt` feeds only backend options (`nfconfig.py`), never pipeline params. No alignment
  input seam exists on `contig run` (`cli.py:357-387`).
- Even in a hypothetical future seam, sarek's reference wiring (`--fasta` → GATK
  `--reference` / samtools `-T`) would suppress the "CRAM requires reference" failure the
  conversion would fix.
- The only CLI surface that accepts an alignment path (`verify --concordance-auto --bam`)
  always passes `-f <ref>` (`verification/second_caller.py:47-58`) — htslib autodetects
  CRAM-vs-BAM by magic bytes, so even there no format failure can occur.

This is structurally identical to the bwa-mem2 slice (v0.11.0), which shipped
**detector-only** for the same reason ("cannot be produced by a Contig-launched run today")
and is the template. A convert-and-retry heal would be dormant machinery that never fires —
against CLAUDE.md #2 (harden real run/verify surfaces, not hypotheticals). The issue card
anticipated this fork: "if none exists, ship detector-only like the bwa-mem2 slice"
(`docs/planning/_card/issue.md`).

## Scope therefore: detector + corpus only (CRAM→BAM direction)

- **New `FailureClass`** `alignment_format_mismatch` (additive member of the 18-literal
  Literal, `models.py:262-281`; propagates automatically to the LLM-detector prompt
  whitelist and corpus label types).
- **Narrow detector branch** in `diagnose_failure` (`detect.py:62-423`), placed before the
  `tool_crash` fallthrough (`detect.py:408`), after the `missing_index` family
  (`detect.py:213-329`) whose absence needles could steal the case. Currently these errors
  classify as `tool_crash` at confidence 0.4 — the taxonomy gap this closes.
  Candidate phrase signatures (REASONED, not observed — no real CRAM log exists in the
  repo): htslib `[E::cram_decode_slice]` reference-required family; `Reference file is
  required for CRAM`; GATK `Reference is required for CRAM`. Direction: CRAM→BAM is the
  only plausible real-world failure (CRAM is the space-saving output format; BAM is the
  universal interchange; no registered pipeline requires CRAM input). BAM→CRAM explicitly
  out of scope.
- **One golden corpus case** (real-quoted source string, `source:"synthetic"`, seeded per
  the one-per-kind tradition) + **holdout twin** (mirrors `holdout-reference-not-bgzf`).
- **Heal-guard scenario**: a give-up scenario (diagnosis fires, no patch proposed, honest
  `gave_up`) mirroring the `reference_recompress_unresolvable` give-up twin pattern —
  the loop must classify and terminate honestly, never a false pass. Requires `covered_classes`
  to move and a deliberate `--update-baseline` refreeze.
- **No repair, no redirect, no conversion.** The run ends in an honest FAIL exactly as
  `tool_crash` does today — but now labeled correctly (better diagnosis text on the
  dashboard, corpus fuel, and the day an alignment-input seam exists the repair has a home).

## Template chain to mirror (bgzip slice)

- Detector branch: `detect.py:387-404` (`reference_not_bgzf`: needle anchoring lesson —
  NOT the bare "please use bgzip" shared with tabix/bcftools; confidence 0.85).
- `FailureClass` literal: `models.py:262-281` (`reference_not_bgzf` at :267).
- Corpus case shape: `src/contig/data/detector_corpus.jsonl:24` (`reference-not-bgzf`).
- Holdout twin: `src/contig/data/detector_corpus_holdout.jsonl:13`.
- Heal scenario shape: `src/contig/data/heal_scenarios.jsonl:11` (heal twin :15 — give-up
  pattern; note the outcome-assertion caveat: scenarios assert the outcome string, never
  `detail`, so a give-up shared across guards is indistinguishable — bwa-mem2 used
  `index_unresolvable`; here the honest terminal is the plain `gave_up`).
- Driver: `src/contig/heal.py` — `HealScenario` (`models.py:555-603`), `_scripted_executor`
  (`heal.py:101-114`), artifact directives (`_write_fasta_artifact` `heal.py:54-70`); the
  new scenario needs no artifact directive (no repair to exercise — pure detection + give-up).
- Baseline refreeze: `contig heal-guard --update-baseline` (`cli.py:2734-2843`) → deliberate
  act, `heal_history.jsonl` append-only.
- `eval-guard`: the new corpus case lands in the **training** corpus; the holdout is
  untouched, so `eval-guard` should be unmoved (92.3%) — if it moves, that is a red flag
  (holdout must not be edited).

## Honest limits (the standing disclosure, stated up front)

- Push, not demand-pull; organic frequency **unmeasured** — the field corpus has only ever
  seen `oom`/`tool_crash`/`missing_index`/`unknown`.
- The needle is **reasoned, not observed** (no real nf-core in CI; no real CRAM error in the
  repo; a non-matching CRAM error still degrades to `tool_crash`).
- The accuracy gain is **self-graded** (we write the fixture we grade) — the bwa-mem2
  disclosure verbatim.
- **It recovers nothing for a user** — it changes what the record *says*, not what the
  engine *does*. The only new behavior is a better label and root-cause text for a class
  that cannot currently occur.

## Contradictions / open questions surfaced

1. The roadmap phrase "CRAM↔BAM conversion" implies convert-and-retry; the dig settled the
   fork the card named: detector-only. This is a **scope change**, not a silent shrinking —
   flag at the review gate, offer the alternates (C1 "corroborated by" surface; C6
   concordance-family capture) as pivots if the user prefers a larger unit.
2. `read_task_errors` hardcodes `<run_dir>/work` (`runner.py:1131`) vs `target.work_dir`
   (`nfconfig.py:100`) — a pre-existing gap, out of scope here, noted so a future real
   trigger hunt is not surprised by it.
3. `built_paths` one-per-run guard and outcome-literal naming only matter if a repair ever
   ships; deferred with the repair.
