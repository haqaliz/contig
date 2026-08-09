# PRD: self-heal-cram-bam-conversion — CRAM/BAM format-mismatch detection (C2)

- **Slug:** `self-heal-cram-bam-conversion`
- **Type:** feat · **Owner:** aliz · **Branch:** `feat/self-heal-cram-bam-conversion/aliz`
- **Capability:** C2 (self-heal breadth) — the input-format-conversion class's second half,
  scoped by reachability (see Problem Statement and R1).
- **Source:** inline brief (`docs/planning/_card/issue.md`) + deep-dig
  (`docs/planning/self-heal-cram-bam-conversion/understanding.md`).

## Problem Statement

Contig's failure detector (`diagnose_failure`, `src/contig/detect.py`) has no branch for
alignment-file format errors: a tool that dies because it cannot decode a CRAM alignment
(the htslib/GATK "CRAM requires a reference" family) or because it was handed a file in the
wrong alignment format is classified as the generic `tool_crash` at confidence 0.4 — an
opaque, mislabeled diagnosis. This is the input-format-conversion class's second half, which
the bgzip-reference slice explicitly deferred ("**Deferred:** CRAM↔BAM conversion (the other
half of this class)" — `docs/planning/self-heal-bgzip-reference/prd.md:187`).

**The reachability finding settles the scope.** No Contig-launched run can produce this
failure today: the samplesheet models are FASTQ-only (`samplesheet.py:11-15, 18-32` — a
BAM/CRAM sarek sheet is refused at pre-flight as missing `fastq_1`, `cli.py:589-593`), the
launch argv is mechanically `--key value` over params (`runner.py:1149-1181`), and even a
hypothetical alignment-input seam would be suppressed by sarek's wired `--fasta` reference.
This is structurally identical to the bwa-mem2 slice (v0.11.0), which shipped
**detector-only** for the same reason and is the template. A convert-and-retry heal
(samtools view into scratch + params redirect) would be dormant machinery that never fires —
against `CLAUDE.md` #2 (harden real run/verify surfaces, not hypotheticals).

So this slice ships the **honest half**: a new `FailureClass`, a narrow detector branch, and
the corpus/guard seeds — so the class is labeled correctly the day it occurs (better
diagnosis text on the dashboard, corpus fuel, taxonomy gap closed), with the conversion
repair deferred behind a committed revisit trigger (R4).

**Evidence it's real:** the class is documented (CRAM is reference-based; decode without
reference is a genuine, well-known htslib/GATK failure family), and it is currently
mislabeled `tool_crash` (no needle matches; `detect.py:408-417` fallthrough). The needle is
**reasoned, not observed** — no real CRAM error has ever been seen in a Contig run, and the
field corpus has only ever diagnosed `oom`/`tool_crash`/`missing_index`/`unknown`
(`docs/technical/CAPABILITY_ROADMAP.md`, C2 honest-limits record).

## Goals & Success Metrics

- **G0 — Honest success axis, stated up front.** This slice moves **no reliability metric**:
  unattended-completion is untouched (the class is unreachable today; see Problem
  Statement). Success is, and is only: (a) a closed taxonomy gap — the class has a name, a
  branch, and corpus support before the first real case can arrive; (b) a working relabel
  channel (R7) so a human can correct a future misdiagnosed case into it before it is
  counted; (c) corpus fuel that compounds ahead of the trigger. If (a)-(c) are not worth a
  committed slice to the reviewer, the honest alternative is a two-line C2 deferral-record
  note — this PRD exists because the bwa-mem2 precedent (v0.11.0) shipped the same shape.
- **G1 — Correct classification.** A failed task whose log carries a CRAM/BAM
  format-mismatch signature is diagnosed `alignment_format_mismatch` with a root cause and
  confidence, never the `tool_crash` fallthrough. *Metric:* corpus case + a direct
  `diagnose_failure` test on a log fixture; detector guard holds at its committed baseline.
- **G2 — Zero over-match, both directions.** No shipped failure class regresses: the new
  branch is narrow (AND-guarded on CRAM/format tokens) and ordered so it cannot steal
  `missing_index` (absence needles), `missing_reference`, or `bad_param` cases, and cannot
  match the bgzip/VCF phrase family. *Metric:* the existing detector corpus suite stays
  green unchanged; **two control tests** —
  (i) a genuine `missing_index`-shaped log (e.g. `stale-bai`) still classifies
  `missing_index` with the new branch present, and (ii) a CRAM error line that *also*
  contains an absence phrase or path token still classifies `alignment_format_mismatch`
  (branch placement + narrow AND-guard working together).
- **G2b — Guard discipline on the holdout append.** R3 appends a twin to
  `detector_corpus_holdout.jsonl`, which changes the holdout's `corpus_sha` — so
  `eval-guard` reports `sha_mismatch` loudly and the baseline is **refrozen with
  `--update-baseline` as the deliberate, documented act** (never a hand-edit). The
  refrozen number is honestly recomputed over 14 cases and disclosed as a **corpus
  composition change, not an accuracy improvement** (the standing `recovery_rate`
  disclosure); if the twin misclassifies, that is a disclosed known-miss, never a silent
  pass. Training-corpus-only slices (bwa-mem2) needed no refreeze; a new class needs the
  twin, so this slice does.
- **G3 — Honest terminal behavior.** A run diagnosed `alignment_format_mismatch` with no
  repair path ends in an honest give-up (never a false pass, never a fabricated patch). A
  heal-guard scenario pins this. *Metric:* one frozen scenario with
  `expected_outcome: "gave_up"`, `expected_recovered: false`, `expected_patch_applied:
  false`; `--update-baseline` refreeze as a deliberate act.
- **G4 — Reproduce-safety preserved.** Nothing about the detector change alters the launch
  manifest, params, or verdict surface; no signed-record field changes. *Metric:* full suite
  green; no signature-breaking test added.

## User Personas & Scenarios

- **Lone computational biologist (A)** running sarek: today, a CRAM-decode failure reads as
  a baffling `tool_crash`; after this slice it reads as a named format mismatch with an
  honest explanation — even though no Contig-launched run can hit it yet, the diagnosis
  text is the artifact.
- **Core facility / facility pipeline integrator (C)**: the taxonomy gap is most visible in
  the pending-corpus review workflow, where a future mislabeled case would be promoted with
  the wrong class; this slice ensures the class exists to be relabeled into.

Primary "user" of this slice is the corpus/detector machinery itself (moat #2), not an
interactive flow.

## Requirements

### Must-have

- **R1 — New `FailureClass` literal `alignment_format_mismatch`** (additive member of the
  18-literal `FailureClass` Literal, `models.py:262-281`). Must propagate without extra work
  to the LLM-detector prompt whitelist and the corpus label types (verified pattern: the
  bwa-mem2 `missing_index` reuse and the literal's auto-propagation).
- **R2 — Narrow detector branch** in `diagnose_failure` (`detect.py:62-423`), placed after
  the `missing_index` family (`detect.py:213-329`) and before the `tool_crash` fallthrough
  (`detect.py:408`). AND-guarded on a CRAM/format token plus a decode-failure phrase, so it
  neither over-matches nor collides with the shipped absence-needle branches (the
  faidx-vs-bgzip anchoring lesson, `detect.py:387-390`). Emits `root_cause` naming the
  format problem and a confidence (0.85, matching the sibling slices' honest tier).
  Reasoned candidate signatures (marked reasoned-not-observed in the code comment and here):
  htslib `[E::cram_decode_slice]` reference-required family; `Reference file is required for
  CRAM`; GATK `Reference is required for CRAM`. Direction: **CRAM→BAM flavor only**
  (CRAM-as-input-to-a-reference-wired-consumer); BAM→CRAM has no plausible consumer and is
  out of scope (R9).
- **R3 — One golden corpus case** seeded in `src/contig/data/detector_corpus.jsonl`
  (per-kind tradition; the bwa-mem2 case is the template — real-quoted source string,
  `source: "synthetic"`, `expected_class: "alignment_format_mismatch"`) **plus a holdout
  twin** in `detector_corpus_holdout.jsonl` (`holdout-…` id, disjoint from training ids).
  **The twin is written FIRST, before the branch needles are chosen**, from an
  independently authored framing of the failure (different vendor wording: htslib
  `[E::cram_decode_slice]` reference-required vs GATK "Reference is required for CRAM"),
  and the branch is then validated against it — the `holdout-no-progress-1`
  independent-author lesson made mechanical. A twin that is a re-wording of the training
  case tests the author's paraphrase, not the branch.
- **R4 — One heal-guard give-up scenario** in `src/contig/data/heal_scenarios.jsonl`:
  attempt 1 fails with the CRAM signature → classified `alignment_format_mismatch` → no
  patch proposed → honest `gave_up`, `expected_recovered: false`,
  `expected_patch_applied: false`. `covered_classes` moves 15 → 16 with a deliberate
  `--update-baseline` refreeze (`heal_baseline.json` + append-only `heal_history.jsonl`).
- **R5 — Honest no-false-pass contract**: no repair, no retry, no params redirect; the
  detector-only scope means the loop's existing no-patch path terminates the run exactly as
  `tool_crash` does today — only the label and root-cause text change. No signature break,
  no `models.py` field additions beyond the literal.

### Should-have

- **R6 — Evidence surfaced correctly**: the diagnosis's `evidence` lines carry the matched
  CRAM/format lines, and `RepairStep.detail` (where applicable) names the class's honesty
  tier — no patch was available by design (mirrors the advisory disclosure pattern).
- **R7 — Dashboard taxonomy in sync**: the `FAILURE_CLASSES` list in
  `dashboard/lib/derive.ts` (server-validated in
  `dashboard/app/api/corpus/promote/route.ts`) gains the new literal so a human can relabel
  a pending case into it (the v0.51.0 `FAILURE_CLASSES` 13→18 fix is the template).

### Nice-to-have

- **R8 — A `--rev`-style audit note** in the changelog: the conversion repair stays deferred
  behind the revisit trigger, so a later slice finds the record.

## Technical Considerations

- **No new dependency.** The engine contract is stdlib + `pydantic`/`typer`/`cryptography`
  (`pyproject.toml:30-34`). Detection is pure string/line matching over the existing
  `log_text` — no subprocess, no htslib. The repair (samtools view) is deliberately not
  built (R5).
- **Detector ordering is load-bearing** (the standing lesson from every C2 slice): the new
  branch sits after the `missing_index` family (whose absence needles could otherwise steal
  the case) and before `tool_crash`; a control test pins that a genuine `missing_index`
  fixture (e.g. `stale-bai`) still classifies `missing_index` with the new branch present.
- **Corpus mechanics**: training case → `eval-guard`'s held-out baseline must stay unmoved
  (92.3%) — the holdout file is untouched, its `corpus_sha` unchanged; the guard reports
  *unchanged*, never *regressed*. Heal scenario → `covered_classes` 15 → 16, `outcome-match`
  stays 1.0 over 22 scenarios, `recovery_rate` informational-only.
- **Dashboard sync** (R7): `FAILURE_CLASSES` is pinned by tests with a relabel round-trip
  (v0.51.0 pattern) — the new literal must be added to both `derive.ts` and the server
  validator, with the Python-side 19-literal list as the source of truth (order: Python's
  Literal order).
- **Verification/verdict surface**: untouched. This slice changes diagnosis only; no QC
  result, no verdict, no exit-code change.

## Risks & Open Questions

- **R1 — The needle is reasoned, not observed.** No real CRAM error exists in the repo, no
  real nf-core run in CI. If a real CRAM error's wording diverges, it still degrades to
  `tool_crash` — honest, but the slice's value is then taxonomy-only. Mitigation: narrow
  AND-guard on the strongest htslib token (`cram_decode_slice` / "CRAM") + a decode phrase;
  committed revisit trigger: first real-world report of a CRAM failure whose wording misses
  the branch.
- **R2 — Self-graded accuracy.** We author the fixture we grade. The standing disclosure
  (bwa-mem2 verbatim) is written into the changelog; the holdout twin is written FIRST and
  independently framed (R3), and the branch is validated against it — so the guarded number
  is at least testing the branch against wording the branch was not fitted to.
- **R3 — `covered_classes` invites over-reading.** 16 classes have a frozen scenario, which
  is not a claim the engine handles those failures well; the scenario is a give-up, by
  design.
- **R4 — Why now, stated.** The class is unreachable today; the value is the relabel
  channel (a mislabeled pending case can be corrected only if the literal exists), corpus
  training ahead of the trigger, and the bwa-mem2 precedent. If the reviewer weighs those
  below the cost of a committed slice + refreeze, the fallback is a two-line deferral note —
  this PRD argues the slice, not the note.
- **Q1 — Phrase selection**: which exact needles survive the narrow-AND test is an
  implementation decision; the branch must be validated against every existing corpus
  fixture (full suite) plus the control tests.
- **Q2 — Confidence**: 0.85 matches the sibling tier; could argue for 0.8 given
  reasoned-not-observed. Default 0.85, adjustable in review.
- **Q3 — Ordering vs `bad_param`**: a CRAM error could arguably read as a bad parameter
  (wrong file given). The branch order and needles must make the intent explicit (format
  failure wins over param misconfiguration for a file the pipeline was handed); flagged, not
  yet ruled.

## Out of Scope

- **R8 — The CRAM→BAM conversion repair itself** (detect → `samtools view -b` → scratch
  redirect → retry): deferred behind a committed revisit trigger — the first real
  CRAM-format failure observed in a Contig-launched run, or the day an alignment-input seam
  lands. This PRD does not build it, does not stub it, and does not claim it.
- **BAM→CRAM** direction (no plausible consumer).
- The **`.csi`-for-BAM/CRAM index kind** (separate deferred C2 item — the index, not the
  format).
- The `read_task_errors` `--work-dir` blindness (`runner.py:1131` vs `nfconfig.py:100`):
  pre-existing gap, filed, out of scope.
- **No verdict/exit-code/`--fail-on-verdict` change**; no launch-manifest or signed-record
  change.

## Non-Functional Requirements

- **Test-first, deterministic, offline**: no real nf-core, samtools, GATK, network, or pip
  in CI; all fixtures are on-disk synthetic logs; the heal scenario replays through the real
  `self_heal_run` with the scripted executor seam (`heal.py:101-114`).
- **Full suite green** after the slice (`uv run pytest`; 2479 passed, 1 skipped at base) and
  the dashboard build/lint if R7 ships.
