# PRD -- runtime-reference-mismatch-detector

> Unit of work: `feat/runtime-reference-mismatch-detector/aliz`. Source: inline
> brief (docs/planning/_card/issue.md). Interview decisions (2026-08-24): tight
> contig-absence needle family; full slice across all layers; planning slug
> `runtime-reference-mismatch-detector`.

## Problem Statement

A wrong reference is the most dangerous silent-failure class in bioinformatics: a
run "succeeds" against the wrong genome. The pre-flight half of this family is
shipped (v0.7.0 contig-naming refusal, chr-prefix harmonization, per-contig alias
harmonization), and every one of those slices explicitly recorded the runtime
half as deferred: "no new `reference_mismatch` `FailureClass` or detector-corpus
case" (CHANGELOG:2968, :3282). The C2 deferral list still names "a runtime
`reference_mismatch` detector-corpus case" (CAPABILITY_ROADMAP.md:512-516).

Today, a hard-failing task whose log says the reads' contigs are absent from the
reference -- e.g. STAR `Contig 'chr1' not found in the reference dictionary
/work/ref/genome.fasta`, `sequence 'chr1' not found in the reference genome …` --
classifies `tool_crash` at confidence 0.4 (verified empirically:
`src/contig/detect.py:434-445`). The wrong-genome family is invisible in the
failure corpus, the diagnosis is unactionable, and the C2 deferral stays open.
The missing-index branches deliberately decline this family
(`detect.py:249-251, :316-317`); the two shipped negative tests
(`tests/test_detect.py:272-284, :331-337`) pin exactly these logs as
`!= missing_index` -- they are the seed of this slice.

**What happens if we don't build this:** the family stays `tool_crash` at 0.4,
uncountable in the corpus, unmovable for the eval/heal guards; the deferral stays
open. The slice *recovers nothing* (honest give-up, same as
`alignment_format_mismatch`) -- it renames a diagnosis, seeds the corpus, and makes
the family measurable. Push, not demand-pull; organic frequency unmeasured.

## Goals & Success Metrics

| Goal | Metric | Current | Target |
|---|---|---|---|
| The wrong-reference hard-fail gets its own class | FailureClass literals | 19 | 20 (`reference_mismatch`) |
| Detector recognizes the family | eval-guard held-out accuracy | 92.9% (13/14), known miss `holdout-qc-anomaly-1` | ≥ 92.9%; 14/15 if the twin classifies; baseline refrozen deliberately |
| Golden corpus stays perfectly classified | training corpus accuracy (tests/test_corpus.py:146-153) | 100% (27/27) | 100% (28/28) |
| Loop behavior guarded | heal-guard outcome-match | 1.0 (22 scenarios) | 1.0 (23 scenarios), covered_classes 16 → 17 |
| No false attribution | `qc_anomaly` family never double-classified | structural (success path only) | pinned by test |
| Taxonomy mirrors everywhere | dashboard FAILURE_CLASSES + e2e length pin | 19 | 20, same order |
| No regression | full suite | 2666 passed / 1 skipped | green (≈2670+); no signature break |

## User Personas & Scenarios

- **Persona A (lone computational biologist)** and **Persona B (wet-lab, cannot
  code)** run a `contig run` whose reads/FASTA disagree with the selected
  reference. Today: the run fails with a generic tool-crash diagnosis.
  After: `contig show`/dashboard names `reference_mismatch` with the matched
  evidence lines and an honest give-up (`no repair proposed`), and the case lands
  in the pending corpus for the human review loop.
- **Corpus curator (the founder / reviewer)**: the Pending-review tool can now
  confirm/correct a `reference_mismatch` provisional label (dashboard
  `FAILURE_CLASSES` gains the literal), and promote the real-run case into the
  golden corpus -- the compounding loop (moat #2).

## Requirements

### Must-have

- **R1 -- Literal.** Add `"reference_mismatch"` to `FailureClass`
  (`src/contig/models.py:262-282`, 19 → 20). The valid-class set is derived
  (`detect.py:519`), so no manual sync in the engine. No signature break
  (precedent `tests/test_signing.py:218-289` -- a Literal adds no field).
- **R2 -- Detector branch.** New narrow branch in `diagnose_failure`, placed after
  `alignment_format_mismatch` (`detect.py:414-432`) and before `tool_crash`
  (`:434`), confidence **0.85**, AND-guarded:
  - primary phrase: contig-absence from the reference (e.g. `not found in the
    reference dictionary`, `not found in the reference genome`, `sequence '…'
    not found in the reference`) **AND** a contig/sequence token
    (`contig`/`sequence`/`chr`-shape) -- the tight family per interview decision;
  - must NOT match the `missing_index` family (no index token -- `:226-329` must
    keep winning their own logs) and must NOT match `missing_reference` (which
    needs `no such file or directory` AND a ref token, `:331-340`);
  - GATK `incompatible contigs` wording is **excluded** by decision (control
    negative: stays `tool_crash`), recorded in the branch comment;
  - the **exact needle tuple is pinned by the plan's failing tests** (the
    tech-plan names the literal phrase strings; the tests are the contract);
  - hand-written `root_cause` naming the wrong-reference condition; evidence via
    `_matching_lines` (`:23-30`).
- **R3 -- Golden corpus case.** One case in `detector_corpus.jsonl` (27 → 28,
  `case_id: reference-mismatch-…`, `source: synthetic`), classifying correctly so
  the training-corpus guard stays 100%.
- **R4 -- Holdout twin.** One **independently authored** twin in
  `detector_corpus_holdout.jsonl` (14 → 15, `holdout-` id,
  `source: holdout:synthetic`) -- second author, different tool wording (the
  `cram-reference-required` precedent: htslib training vs GATK holdout,
  `tests/test_eval_holdout.py:75-84`). Twin pin test mirroring that precedent.
  Refreeze `holdout_baseline.json` via `contig eval-guard --update-baseline`
  (13/14 → 14/15 if it classifies; otherwise a **disclosed known-miss** and the
  baseline stays 92.9% -- either is acceptable, never a silent number).
- **R5 -- heal-guard give-up scenario.** One scenario in `heal_scenarios.jsonl`
  (22 → 23), near-clone of `alignment-format-mismatch-give-up` (line 22):
  `expected_class reference_mismatch`, `expected_recovered false`,
  `expected_outcome "gave_up"`, `expected_patch_applied false` (propose returns
  `[]` -- `repair.py:14-183` has no branch, and that is the honest contract).
  covered_classes 16 → 17; update `tests/test_heal_scenarios.py:791-817`
  (16 → 17); refreeze `heal_baseline.json` via
  `contig heal-guard --update-baseline`; **outcome-match must stay 1.0**;
  `recovery_rate` stays informational (11/22).
- **R6 -- Taxonomy sync + stale doc.** `dashboard/lib/derive.ts:278-298`
  (FAILURE_CLASSES mirror, same order);
  `dashboard/e2e/failure-classes.spec.ts:26-59` (length 19 → 20, `PYTHON_ORDER`
  gains the literal in position);
  `dashboard/e2e/promote-label-validation.spec.ts:14-22` extended (the round-trip
  precedent for the new label); promote route auto-accepts
  (`dashboard/app/api/corpus/promote/route.ts:28` -- no change, verify);
  fix the **already-stale** heal-guard docstring `src/contig/cli.py:3079-3118`
  ("15 covered classes", "3 of the 18 literals"; actual 16 of 19 -- becomes 17 of
  20).
- **R7 -- Flip/extend the shipped negatives.** `tests/test_detect.py:272-284`
  and `:331-337` become **positive** `reference_mismatch` coverage (same logs),
  keeping their negative intent for `missing_index`; add the family's standard
  controls (a genuine `missing_index`/`missing_reference` log must still classify
  its own class; the GATK incompatible-contigs log stays `tool_crash`).
- **R8 -- `qc_anomaly` non-overlap pin.** A test proving a wrong-reference-shaped
  log on the **success path** (green tasks, QC FAIL) stays `qc_anomaly` and never
  reaches the new branch -- the two families are structurally disjoint
  (`qc_anomaly` is synthesized in `self_heal.py:1233-1302` on succeeded runs;
  `diagnose_failure` only sees failed-task events, called at `self_heal.py:1311`).
- **R9 -- CHANGELOG.** Honest entry: reasoned-not-observed needle, self-graded
  fixtures, push-not-demand-pull, recovers nothing, eval-guard move (if any) is
  partly self-graded, the GATK-phrase exclusion, and the refrozen baselines as
  deliberate acts.

### Should-have

- **S1 -- Safety-net test.** Mirror `test_every_shipped_no_progress_fixture_still_classifies`
  (`tests/test_detect.py:654-677`): walk the shipped corpora + heal scenarios and
  assert every `reference_mismatch` fixture still classifies, ahead of guard time.
- **S2 -- History snapshots.** `contig eval-guard --snapshot` and
  `contig heal-guard --snapshot` appended trend points (append-only history).

### Nice-to-have

- **N1 --** A friendly label for the new class in the remaining label maps
  (fallback covers it; `repair-timeline.tsx:25` already has the key).

## Technical Considerations

- **Branch placement:** after `alignment_format_mismatch`, before `tool_crash`
  -- mirrors the CRAM precedent; no reordering of the stall/OOM priority head.
- **Guard discipline:** the family's standing rule is narrow-AND; the branch must
  be anchored so the six `missing_index` branches (`detect.py:213-329`) and
  `missing_reference` keep winning their own logs. The two shipped comments
  (`:249-251, :316-317`) already reserve this family for its own class.
- **Baselines are deliberate acts:** every refreeze via `--update-baseline`,
  never a hand-edit; `corpus_sha` changes are expected and must be recorded.
- **`strict` detector:** `diagnose_failure_strict` (`:469-502`) demotes only
  `platform_unsupported`/weak `conda_solve_failed` -- an 0.85 branch is unaffected.
- **Dependencies:** none new (stdlib-only holds). No model field, no signed
  payload change, no `verify`/verdict/exit-code change.

## Risks & Open Questions

- **🔴 Reasoned-not-observed needle.** No real mismatched-reference run exists in
  CI; the fixture and the branch are self-graded (we author what we grade -- the
  `no_progress` disclosure precedent). Mitigation: the independent holdout twin;
  disclosed in CHANGELOG, never oversold. A non-matching real-world wording still
  degrades to `tool_crash` honestly.
- **🟡 Over-match risk.** If the primary phrase is too generic (e.g. bare
  `not found in the reference`), it can steal `missing_reference`-adjacent logs.
  Mitigated by the AND-guard token and control negatives; the tight family was
  the interview decision.
- **🟡 Self-graded eval-guard move.** If the twin classifies, 92.9% → 14/15 is
  partly a function of a fixture we wrote; the `qc_anomaly` known-miss must stay
  the only miss or be disclosed.
- **🟡 GATK `incompatible contigs` exclusion.** A deliberate decision; a real
  GATK wrong-reference hard-fail stays `tool_crash`. Revisit trigger: first real
  report (no demand signal today).
- **Open:** none blocking -- the three interview decisions closed the set.

## Out of Scope

- **Any repair/patch** for `reference_mismatch` (no live trigger; honest give-up
  only -- same verdict as CRAM↔BAM).
- **Assembly-signature pre-flight form** of reference/build mismatch (blocked: no
  sample-side contig signal in raw FASTQ or finished bundle).
- **GATK `incompatible contigs`** branch wording (excluded by decision; control
  negative).
- C5 known-sites / GTF-version / RO-Crate slices; pin-conflict repair; the rest
  of the C2 wider catalog.
- FAIL severity, verdict changes, exit-code changes, `--fail-on-verdict`
  interaction.
- Real nf-core run in CI (manual post-merge smoke gate, per every sibling slice).

## Data Model

No schema change. New values only: one `FailureClass` literal; one
`FailureCase` in each of `detector_corpus.jsonl` / `detector_corpus_holdout.jsonl`;
one `HealScenario` in `heal_scenarios.jsonl`; refrozen
`holdout_baseline.json` / `heal_baseline.json`; mirrored
`dashboard/lib/derive.ts` `FAILURE_CLASSES`.