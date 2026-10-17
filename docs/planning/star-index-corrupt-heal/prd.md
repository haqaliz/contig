# PRD: star-index-corrupt-heal (C2, self-heal breadth)

Status: draft for review. Owner: aliz. Branch: `feat/star-index-corrupt-heal/aliz`.
Sources: `docs/planning/_card/issue.md` (inline brief, `/contig-next` handoff
2026-10-17), `docs/planning/star-index-corrupt-heal/understanding.md` (Phase-2 dig),
`docs/planning/self-heal-dir-index/prd.md:153` (the N1 deferral), C2 in
`docs/technical/CAPABILITY_ROADMAP.md`.

Capability: **C2 (self-heal breadth plus auto resource-scaling), follow-on slice N1.**

## Problem Statement

A STAR genome index that is **corrupt or partially built** fails the aligner with
STAR's `EXITING because of FATAL GENOME INDEX FILE error: <file> is corrupt, or is
incompatible with the current STAR version` (confirmed against real reports, e.g.
`transcriptInfo.tab is corrupt, or is incompatible with the current STAR version`,
alexdobin/STAR#978). The message names **only the offending file's basename**, with no
directory path. Contig's runtime detector recognises STAR's *missing* index
(`genomeParameters.txt` / `could not open genome file`) and *version-incompatible*
index (`Genome version` + `INCOMPATIBLE`) as `missing_index` and heals both by
rebuilding the index into run-scoped scratch and retrying
(`src/contig/detect.py:267-295`, `src/contig/self_heal.py:653-760`). The **corrupt**
flavour matches none of those needles, so it falls through to `tool_crash` at
confidence 0.4 (`detect.py:456-465`), the loop never diagnoses it, never rebuilds,
and the run ends in an honest but useless FAIL, burning the user's compute and their
time on a failure the engine already knows how to fix.

This is squarely the moat (`CLAUDE.md`): *recover more failures without a human*, and
raise the ROADMAP Phase-1 unattended-completion metric (`docs/ROADMAP.md:101`).

**Evidence it's real.** This exact signature was catalogued and deliberately deferred
as **N1** by the shipped STAR/BWA directory-index slice: *"`FATAL GENOME INDEX FILE
error ... is corrupt`, deferred this slice (rarer; same rebuild heal, easy
follow-on)"* (`docs/planning/self-heal-dir-index/prd.md:153`); it also stands in C2's
deferred list (`docs/technical/CAPABILITY_ROADMAP.md:556`). The rebuild heal the fix
reuses is shipped and green. There is no incumbent that recovers this at all.

## Goals & Success Metrics

- **G1, Detect the corrupt STAR index.** A failed-task log carrying STAR's corrupt
  phrasing classifies as `missing_index` at 0.85 with the matched line in evidence,
  instead of the current `tool_crash` @0.4. *Metric:* a detector test asserts the
  class, confidence, and evidence; the shipped corpus guard stays at 100%.
- **G2, Heal it end-to-end without a human.** With `--auto-approve` (the shipped
  posture for `missing_index`; the patch stays `needs_confirmation`,
  `repair.py:56-65`), the loop routes to `_build_star_index`, redirects
  `params["star_index"]` to scratch, retries, and records
  `built_index_and_retried`. *Metric:* a heal-guard scenario replays the **real**
  loop to that outcome; guarded `outcome_match_rate` stays 1.0.
- **G3, No regression, no false positives.** `missing_index` handling for the
  existing STAR/BWA/single-file flavours is byte-identical; a corrupt-looking line
  that is not the STAR phrase stays `tool_crash`; a single-file token is never stolen.
  *Metric:* negative-control tests; the four CI guards stay green.
- **G4, No new `FailureClass`, no new dependency.** `missing_index` already exists
  (`models.py:276`); no literal/enumeration changes; stdlib only; no
  verdict/exit-code/signature change.

## User Personas & Scenarios

- **A, lone computational biologist:** points Contig at a `--star_index` left over
  from an aborted build (or a transfer-truncated one); today the run FAILs as
  `tool_crash` and they re-run by hand. Wants the engine to rebuild and finish.
- **C, core facility:** a corrupt shared reference index silently breaks a whole
  batch; wants consistent, unattended recovery.

## Requirements

### Must-have (this slice)

- **R1, Detector branch.** A new branch in `diagnose_failure` beside the existing
  STAR branches (`detect.py:267-295`), **AND-guarded** on a STAR corrupt phrase
  (`FATAL GENOME INDEX FILE error`) **plus** a corruption token (`corrupt`),
  returning `failure_class="missing_index"`, confidence **0.85**, with the matched
  line as evidence and a root cause naming the corrupt index. Placed **before** the
  `tool_crash` fallthrough (`:456`).
- **R2, Routing predicate (load-bearing).** Extend `_is_star_signature`
  (`self_heal.py:113-123`) to also match the corrupt phrasing, so
  `_parse_missing_index` (`:126-155`) returns `("" or dir, "star")` and the loop
  dispatches to `_build_star_index` rather than giving up `index_unresolvable`
  (`:1115-1122`). The `_build_star_index` body is **unchanged**.
- **R3, Heal behavior.** The genomeDir resolves from a `<dir>/genomeParameters.txt`
  token when present (unchanged) and otherwise from `params["star_index"]`
  (`self_heal.py:688`). Because the corrupt message carries **no path**, this slice's
  path always uses the `params["star_index"]` fallback; if neither is present the loop
  gives up honestly as `index_unresolvable` (never a false repair). The build writes
  `run_dir/healed_index/star`, redirects `params["star_index"]`, and returns
  `built_index_and_retried`; every give-up stays honest
  (`index_unresolvable` / `index_build_failed`), bounded to one rebuild per path. No
  change to `_build_star_index`'s body.
- **R4, `HealScenario` fixture directive.** Add an additive, defaulted-to-`None`
  field `star_index_artifact` on `HealScenario` (`models.py:587-635`), mirroring
  `stale_index_artifact`/`fasta_artifact`: the driver creates the named index dir
  under the run dir and sets `params["star_index"]`, so the scenario drives the
  **real** `_build_star_index`. Default `None` leaves every existing scenario's
  behaviour byte-identical.
- **R4b, STAR-aware scripted index builder.** `heal.py::_scripted_index_builder`
  (`:118-156`) simulates only single-file tools (`samtools`/`tabix`/`bcftools`) and
  creates **nothing** for a STAR `genomeGenerate` argv, so a STAR scenario with
  `index_builder_result: "success"` would leave the scratch `--genomeDir` empty and
  the heal would give up `index_build_failed`. Add a STAR branch that touches a file
  inside the `--genomeDir` value so the directory build reads as produced. Additive:
  no existing scenario emits a STAR argv.
- **R5, Golden detector case.** One case in `src/contig/data/detector_corpus.jsonl`
  (28 → 29) with STAR corrupt wording and `expected_class="missing_index"`; the
  training-corpus guard (`tests/test_corpus.py:150-153`) stays at accuracy 1.0. No
  holdout twin this slice (see Out of Scope).
- **R6, Heal-guard scenario.** One scenario in `src/contig/data/heal_scenarios.jsonl`
  (23 → 24): first attempt FAILED with the corrupt STAR log, `auto_approve: true`,
  `index_builder_result: "success"` (with the R4b STAR-aware builder populating the
  scratch `--genomeDir`), `star_index_artifact` + `fasta_artifact` seeded,
  `expected_class="missing_index"`, `expected_outcome="built_index_and_retried"`,
  `expected_recovered=true`, `expected_patch_applied=true`. `covered_classes` stays
  **17** (`missing_index` is already covered).
- **R7, Refreeze and count sync.** Refreeze `src/contig/data/heal_baseline.json`
  via `contig heal-guard --update-baseline` (scenario_count 23 → 24, recovery
  rate `X/24`); update the pins in `tests/test_heal_scenarios.py:742-818`
  (`total`, `healed`, `recovery_rate`, baseline `scenario_count`/`recovery_rate`;
  `covered_classes == 17` unchanged); update the heal-guard docstring counts
  (`cli.py:4001` "23", `:4037` "11/23"). `holdout_baseline.json` / `eval-guard` are
  **not** touched (see Out of Scope).
- **R8, Negative controls.** Pin that a genuine STAR *missing* and *version-
  incompatible* line still classify exactly as before; that a `.fai/.bai/…` token is
  still scanned first and never stolen by the corrupt branch (`self_heal.py:143-146`);
  and that a bare `corrupt` mention with no STAR phrase stays `tool_crash`.

### Should-have

- The detector's `root_cause` and evidence make the corrupt index name visible.
- A `CHANGELOG.md` `[Unreleased]` entry in the house format, and the C2 deferral line
  (`CAPABILITY_ROADMAP.md:556`) annotated as closed.

### Nice-to-have (not this slice)

- A holdout twin; a `safe`-risk/auto-approved STAR build; surfacing the STAR sub-cause
  (missing vs corrupt) distinctly in the record.

## Technical Considerations

- **Four production files, not one.** The detector branch is `detect.py`; the heal
  routing is `self_heal.py::_is_star_signature`; the CI-exercise of the heal needs a
  STAR-aware `heal.py::_scripted_index_builder`; and the scenario needs the additive
  `HealScenario.star_index_artifact` field. A detector-only change yields an honest
  `index_unresolvable` give-up, not a recovery, all must ship together.
- **No new `FailureClass`.** `missing_index` is already enumerated everywhere
  (`models.py:276`; `dashboard/lib/derive.ts:282`; the e2e pins at length 20). No
  dashboard/literal/count change.
- **Patch posture unchanged.** `propose_patches` emits the existing
  `needs_confirmation` `build_index` patch (`repair.py:56-65`); `--auto-approve`
  drives the scenario (the `missing_index` house posture). No `risk` change.
- **No raw-read egress**, no new dependency (stdlib only), no models beyond the one
  additive `HealScenario` field, no verdict/exit-code/signature change.
- **Test-first** per the repo's standing discipline; synthetic fixtures; **no real
  STAR / nf-core run in CI** (the STAR build shells out behind the injected
  `index_builder` seam; a real-run check stays a manual post-merge gate).

## Data Model

`HealScenario` gains one optional field:

```python
star_index_artifact: str | None = None
```

Named fixture directive (the `stale_index_artifact`/`fasta_artifact` precedent):
the value is a run-relative genomeDir path; the driver creates the directory and sets
`params["star_index"]`. Additive and defaulted, so it is not a signed-field change and
no existing scenario serialises differently.

## Risks & Open Questions

- **🟡 STAR wording confirmed against public reports, not a captured Contig run.** The
  needle (`FATAL GENOME INDEX FILE error` + `corrupt`) matches the real string in
  alexdobin/STAR#978 (`transcriptInfo.tab is corrupt, or is incompatible with the
  current STAR version`) and the shipped dig table
  (`docs/planning/self-heal-dir-index/understanding.md:98`). It is still not observed
  in a Contig-launched run; if the wording drifts the branch simply never fires
  (degrades to the current `tool_crash`, no false positive). A manual gate confirms it
  against a real corrupt index.
- **🟡 Push, not demand-pull, and the case is "rarer".** Organic frequency is
  unmeasured; the field corpus has only ever diagnosed
  `oom`/`tool_crash`/`missing_index`/`unknown`. **Revisit trigger:** if the next 20
  real diagnosed failures include no corrupt-STAR case, this is restated as
  taxonomy-only.
- **🟡 `genomeParameters.txt`-corruption is already covered** by the existing missing
  branch; this slice specifically covers corruption of a *different* index file
  (e.g. `<dir>/SA`, `<dir>/Genome`), which carries no parseable `<dir>/…` token, hence
  the `params["star_index"]` fallback and the R4 fixture hook.
- **🟢 No signature/verdict/exit impact**; no new class; guards' behaviour on existing
  cases is unchanged (verified by the byte-identical-pre-existing-lines check).

## Out of Scope

- **A holdout twin and any `eval-guard` refreeze**, deliberate this slice (the class
  is already holdout-covered by `holdout-missing-index-1`; the STAR corrupt phrase has
  no genuinely independent sibling wording). `holdout_baseline.json` is untouched.
- **bwa-mem2 / classic-BWA build+redirect**, the BAM/CRAM `.csi` single-file kind, the
  assembly-signature pre-flight form, and CRAM↔BAM conversion, the remaining C2
  deferrals, unchanged.
- **`safe`-risk / auto-approved STAR builds** and per-sub-cause recording.
- **Any Layer-1 workflow authoring, any clinical claim, any new assay.**

## Acceptance (test-first)

Failing tests are written before the code, per the repo's standing discipline:

1. `detect.py`: a corrupt STAR log → `missing_index` @0.85 with the matched line in
   evidence (currently `tool_crash`, genuine RED).
2. Negative controls: the existing STAR missing/version lines still classify as
   before; a `.bai`-bearing corrupt line is not stolen; a bare `corrupt` line with no
   STAR phrase stays `tool_crash`.
3. `self_heal`/`heal.py`: `_is_star_signature` matches the corrupt line; a scenario
   with the corrupt log + seeded `star_index_artifact`/`fasta_artifact` reaches
   `built_index_and_retried` through the real loop.
4. Corpus/guard: `detector_corpus.jsonl` 29 cases, training guard 100%; `heal_scenarios.jsonl`
   24 scenarios, `covered_classes == 17`, guarded outcome-match 1.0; baselines refrozen.

## Self-critique (areas to strengthen before sharing)

- **🟡 Efficacy is capped by `params["star_index"]`.** The corrupt message carries no
  path, so a real corrupt-index run heals only when the user supplied `--star_index`
  (the version-incompatible flavour already has this same limit). When absent, the loop
  gives up honestly, correct, but the slice helps less often than "STAR corrupt index"
  sounds. Stated, not hidden.
- **🟡 Push, not demand-pull; the case is "rarer".** No partner asked; organic frequency
  is unmeasured. The value is breadth on the unattended-completion metric + corpus fuel,
  not a field-proven win. Committed revisit trigger recorded in Risks.
- **🟢 Scope is self-contained and low-risk.** Existing detector/guard behaviour on all
  current cases is provably unchanged (additive branch + additive model field +
  additive scripted-builder arm); no literal, verdict, exit-code, or signature change.
- **Question I'd want answered before greenlighting:** if a corrupt STAR index is only
  healable when the user pinned `--star_index`, is this the *right* C2 slice to spend on now,
  versus one whose recovery has a live trigger in the default (no-`--star_index`) run path?
