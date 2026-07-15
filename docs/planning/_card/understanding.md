# Phase 2 — Understanding: rnaseq-plausibility-ingestion

Dug by three parallel read-only agents (QC call path, unit blast radius, tests) plus direct
upstream verification from the main thread. Every claim is grounded in a file:line or a pinned
upstream source.

**Status: dig complete. The brief's premise is partly WRONG and the design has changed.**
Read the two corrections first.

---

## Correction 1 — this is NOT the single-cell defect class (the important one)

The card (inheriting `CAPABILITY_ROADMAP.md`'s nomination) says `RNASEQ_PLAUSIBILITY_PACK` is
*"the same defect class as the single-cell dormant pack"* — i.e. the metric genuinely never
reaches MultiQC, so a dedicated artifact parser is required.

**That is true for `percent_rRNA`. It is false for `percent_duplication`.**

Verified against pinned upstream sources:

| Fact | Evidence |
|---|---|
| MultiQC's Picard module **does** add duplication to General Statistics | MultiQC `modules/picard/MarkDuplicates.py`: `module.general_stats_addcols(data_by_sample, headers, namespace="Mark Duplicates")` |
| The key is **`PERCENT_DUPLICATION`** (UPPERCASE) | same file: `headers = {"PERCENT_DUPLICATION": {...}}` |
| The stored value is the **raw 0–1 fraction** | same file: values go `float(v)` straight from the metrics table into `data_by_sample`, which is what `general_stats_addcols` stores |
| The `×100` is **display-only** | same file: `"modify": lambda x: util.multiply_hundred(x)` — a header render hook, not applied to stored data |
| nf-core/rnaseq runs MarkDuplicates **by default** | `nextflow.config@3.26.0`: `skip_markduplicates = false` |
| Default aligner / artifact path | `aligner = 'star_salmon'`; docs: `<ALIGNER>/picard_metrics/<SAMPLE>.markdup.sorted.MarkDuplicates.metrics.txt` |

So the metric **is** in `multiqc_data.json` on every real default rnaseq run. Contig misses it
for two independent, compounding reasons:

1. **Case.** The pack asks for `percent_duplication`; MultiQC emits `PERCENT_DUPLICATION`.
   `qc_ingest.py:5-23` does an exact-key merge → the lookup misses → UNVERIFIED, forever.
2. **Scale.** The pack bands `warn_above: 80.0` on a declared 0–100 scale; the JSON carries
   `0.85`. **This is the dangerous half.** A wrong *slug* is safe (UNVERIFIED, never a false
   pass). A wrong *scale* is a **false PASS**: a 96%-duplicated library scores `0.96` against
   `warn_above: 80.0` and silently PASSES. **Fixing the slug without the scale would convert a
   safe dormant check into an actively wrong one.**

**Design consequence:** duplication needs **no new parser, no locator, no `_discover_qc` gate,
no unit-normalization layer**. It is very nearly a pure data edit in `rule_pack.py`. This also
dissolves both risks the agents raised: the sample-id/phantom-sample risk (we reuse MultiQC's
own sample keys) and the merge/unit-collision risk (there is no second source to merge).

`CAPABILITY_ROADMAP.md`'s "silent no-op / same defect class" sentence is what made this look
bigger than it is; it should be corrected in this PR.

## Correction 2 — the pack is dormant but HONEST, not a "silent no-op"

The roadmap calls it a *"silent no-op on every real rnaseq run"*. It does not score, but it is
not silent: `evaluate_rnaseq_plausibility` (`rnaseq_plausibility.py:69-79`) emits an explicit
`unverified` QCResult per absent metric per sample — four on the repo's own demo fixture.

Not pedantic. methylseq/scrnaseq were **true** silent no-ops: their packs ran through the bare
`evaluate()`, which *skips* absent metrics (`rule_pack.py:543-544`). RNA-seq has a wrapper with
a per-metric honesty branch, so its failure mode is **loud**. We are lighting up a metric, **not**
repairing a hole in the verdict's integrity. The PRD must not claim we fixed a false-pass bug:
the current code is honest. The false-pass risk is one we would *introduce* by fixing the slug
alone.

---

## What is really being asked

Make the two RNA-seq plausibility checks produce a real score on a real default
`nf-core/rnaseq@3.26.0` run, without weakening UNVERIFIED-never-PASS, and without touching
severity (WARN-capped stays — see Closed).

Two metrics, **two genuinely different problems**:

### `duplication_rate` — a data bug. Buildable now, high confidence.
Fix the key case (`percent_duplication` → `PERCENT_DUPLICATION`) **and** the band scale
(`warn_above: 80.0` → a 0–1 band). Both halves must land together or we ship a false pass.

### `rrna_contamination` — genuinely the single-cell defect class. Needs a decision.
`percent_rRNA` is **not** a general-stats key from any default rnaseq module; it was guessed.
Verified options:

| Candidate | Default? | Artifact | Catch |
|---|---|---|---|
| SortMeRNA | **NO** — `remove_ribo_rna = false` | `sortmerna/*.sortmerna.log` | not default; dead end |
| featureCounts biotype QC | **YES** — `skip_biotype_qc = false`, `featurecounts_group_type = 'gene_biotype'` | `<ALIGNER>/featurecounts/*_mqc.tsv`, `*.featureCounts.txt.summary` | **GTF-dependent** (needs a `gene_biotype` attribute; a GTF without it skips the step). It is a **biotype counts table** — the rRNA *fraction* must be computed by us, not read off. |

So rRNA is buildable **only** via a dedicated parser of the biotype TSV (the composition-slice
shape), and only when the user's GTF carries `gene_biotype`. Three honest options:
**(a)** build the parser + gate, degrading to UNVERIFIED when the attribute is absent;
**(b)** **drop** the check — precedent: the single-cell slice *deleted* its dead `pct_reads_mito`
rather than keep it; **(c)** keep it UNVERIFIED but retarget its comment at a named artifact.
(a) or (b) are defensible. Leaving a guessed `percent_rRNA` slug in place is not.

**Recommended scope: split.** Ship duplication (data fix, small, high-confidence) as slice 1;
treat rRNA as a separate decision so a hard, GTF-dependent problem doesn't hold the real bug fix
hostage, and so the diff stays honest and reviewable.

---

## Affected areas

- `src/contig/verification/rule_pack.py:295-315` — `RNASEQ_PLAUSIBILITY_PACK`. **The chokepoint.**
  Plus `:298-299` (the misleading METHYLSEQ comment) and `:287-288` (the band contradiction).
- `src/contig/verification/rnaseq_plausibility.py` — **likely zero changes**. Its message
  `"{metric} not reported by MultiQC"` (`:75`) stays accurate for duplication; needs care only
  if rRNA gains a non-MultiQC source.
- `src/contig/runner.py:412-414` — the gate (+ the fiction at `:420-422`).
- `tests/verification/test_run_qc.py:118`, `tests/verification/test_rnaseq_plausibility.py:21` —
  tests that fabricate the wrong slug/scale; must be re-pointed.
- **No** new module, model, `FailureClass`, dashboard card, or dependency for duplication.

## Contradictions / latent bugs surfaced (flag, don't silently fix)

1. **`runner.py:420-422` is a fiction.** *"the MultiQC pack above still owns
   alignment/duplication/rRNA."* It owns duplication **on paper only** — no pack scores it,
   because the key case is wrong. Fixing the slug makes the sentence true for the first time.
2. **`rule_pack.py:298-299` borrows credibility it hasn't earned.** *"Scale 0-100, matching
   METHYLSEQ_RULE_PACK's percent_duplication usage."* Methylseq's 0–100 is **earned** — its
   parser reads an already-percent Bismark artifact (`methylseq_metrics.py:81-84` captures the
   digits inside a literal `%`; fixture `12.34%` → `12.34`). RNA-seq's 0–100 is **declared and
   enforced by nothing**. The two slugs share a name, never a code path. That sentence is
   exactly what made this ambiguity look resolved. Fix it in the same PR.
3. **`multiqc is not None` erases the checks** (`runner.py:412`). With no MultiQC report the
   evaluator is never called and the two checks **vanish** rather than reporting UNVERIFIED. The
   composition gate (`:428`) correctly gates on assay alone. Pre-existing honesty gap; PRD to
   decide: fix here or file separately.
4. **The tests fabricate the bug.** `test_run_qc.py:118`
   `DUP_HIGH_MQC = '{"report_general_stats_data":[{"S1":{"percent_duplication":95.0}}]}'`
   asserts `duplication_rate:S1` WARNs — off a report shape real nf-core/rnaseq **never emits**
   (wrong case AND wrong scale: `95.0`, not `0.95`). Same at `test_rnaseq_plausibility.py:21`.
   **This is how a green suite masked a dead check:** the tests prove the *wiring*, never the
   *ingestion*. Any fix must re-point them at a realistic fixture or we re-ship the blindness.

## The band question — must be decided, not inherited

`rule_pack.py:287-288` says *"A deep/high-input library **legitimately exceeds 90%
duplication**"*, while the band is `warn_above: 80.0`, annotated *"lenient"*. The moment the
metric arrives, **every deep library the pack's own docstring vouches for will WARN.** Invisible
today only because the check has never fired. WARN is not FAIL (no exit-code consequence), so it
does not block the slice — but a tripwire firing on a large share of normal runs is noise, and
noise is how a verdict axis gets ignored (a softer version of the failure this card exists to
fix). Decide explicitly: re-band (~0.90) citing the docstring's own sentence, or keep the
0–1 equivalent of 80 and record that WARNs on deep libraries are expected and acceptable.
**No calibration data exists in the repo; any "typical value" claim would be invented.** The
argument rests solely on the file's internal contradiction, which needs no external data.

## Closed — do not reopen

**FAIL severity.** `CAPABILITY_ROADMAP.md` (C3) records RNA-seq FAIL severity as **declined by
design, not deferred**: every RNA-seq metric has a legitimate protocol occupying its extreme,
*and* severity would sit on code that never fires. This slice removes only the **engineering**
half of that reasoning. **The biological half stands untouched** → both checks stay WARN-capped.
Note honestly: this slice partially invalidates one sentence of that record (the "never once
resolved against a real MultiQC report" claim becomes false for duplication). The *conclusion* is
unchanged; the roadmap's stated *reasoning* needs a small correction so it stays true.

## Guardrails check (CLAUDE.md)

- **Layer 2 only** — verify-axis hardening. Satisfied by construction; no Layer-1 drift.
- **No over-claiming** — WARN-capped; UNVERIFIED-never-PASS preserved; **and we must not
  introduce** the false pass the scale bug would create.
- **No guessed slugs** — the whole defect. Every slug in the fix is cited to upstream source,
  not inferred.
- **Test-first**, stdlib-only, no real nf-core/Picard run in CI.

## Honest limits of this dig (top residual risk)

- **Not verified against a real `multiqc_data.json` from a real rnaseq run.** No such artifact
  exists in the repo: `demo/sample-run/results/multiqc/multiqc_data.json` is **synthetic**
  (generated by `demo/make_sample_run.py`) and carries only `uniquely_mapped_percent`,
  `percent_assigned`, `total_reads`. The `PERCENT_DUPLICATION` key and its 0–1 scale are read
  from MultiQC's **source** — strong evidence, but not an observed artifact. **The PRD must
  state this**, because the scale half is exactly where being wrong yields a false pass rather
  than an honest UNVERIFIED. The UNVERIFIED-when-absent guarantee absorbs a wrong *key*;
  **nothing absorbs a wrong *scale***. If a real report can be obtained, that beats every
  argument here.
- **MultiQC version coupling:** key/scale were read from MultiQC `main`, not the exact MultiQC
  pinned inside nf-core/rnaseq 3.26.0. Worth confirming.
- `dig-artifacts` (the upstream-research agent) never reported; its questions were answered
  directly from upstream sources in the main thread instead. The featureCounts biotype TSV's
  exact column layout is therefore **unconfirmed** — it must be checked before any rRNA parser
  is written.
