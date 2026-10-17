# Spec: detector-and-heal (aspect of star-index-corrupt-heal)

Source: `docs/planning/star-index-corrupt-heal/prd.md`. One cohesive aspect (the slice
is small and the heal depends on the detector's evidence line, so it is planned as one
unit with sequential phases).

## Problem slice and user outcome

A corrupt/partial STAR genome index (STAR's `FATAL GENOME INDEX FILE error: … is
corrupt`) is detected as `missing_index` and healed by the shipped STAR
rebuild+redirect, instead of failing as an opaque `tool_crash`. The user gets an
unattended recovery instead of a dead run.

## In-scope requirements

- **R1** `detect.py`: new AND-guarded branch (`FATAL GENOME INDEX FILE error` +
  `corrupt`) → `missing_index` @0.85, before `tool_crash`.
- **R2** `self_heal.py::_is_star_signature`: also match the corrupt phrasing so
  `_parse_missing_index` routes to `kind == "star"`.
- **R3** Reuse `_build_star_index` unchanged; genomeDir from `params["star_index"]`
  (the corrupt message carries no path); honest give-ups preserved.
- **R4** `models.py::HealScenario`: additive `star_index_artifact: str | None = None`.
- **R4b** `heal.py::_scripted_index_builder`: STAR-aware arm (touch a file inside
  `--genomeDir`).
- **R5** One golden training corpus case (`detector_corpus.jsonl` 28 → 29).
- **R6** One heal-guard scenario (`heal_scenarios.jsonl` 23 → 24) driving the real loop
  to `built_index_and_retried`.
- **R7** Refreeze `heal_baseline.json`; update pins + heal-guard docstring counts.
- **R8** Negative controls.

## Out-of-scope boundaries

Holdout twin / `eval-guard` refreeze; bwa-mem2 / classic-BWA build; BAM/CRAM `.csi`;
assembly-signature; CRAM↔BAM; `safe`-risk builds; Layer-1; clinical claims.

## Acceptance criteria (testable)

1. Corrupt STAR log → `missing_index` @0.85 with the matched line in evidence
   (currently `tool_crash` — genuine RED).
2. Existing STAR missing/version-incompatible lines still classify as before; a
   `.bai`-bearing corrupt line is not stolen; a bare `corrupt` line with no STAR phrase
   stays `tool_crash`.
3. `_is_star_signature` matches the corrupt line; a scenario with the corrupt log +
   `star_index_artifact`/`fasta_artifact` + `index_builder_result: "success"` reaches
   `built_index_and_retried` through the real loop.
4. `detector_corpus.jsonl` 29 cases at 100%; `heal_scenarios.jsonl` 24 scenarios,
   `covered_classes == 17`, guarded outcome-match 1.0; `heal_baseline.json` refrozen;
   `eval-guard`/holdout untouched.

## Dependencies and sequencing

Detector (phase 1) precedes routing (phase 2) precedes the CI-exercise (phases 3-4);
docs/guard sync last (phase 5).

## Open questions / risks

Efficacy is capped by `params["star_index"]` (the message names no path) — see PRD
Risks; wording confirmed against public STAR reports, not a captured Contig run.
