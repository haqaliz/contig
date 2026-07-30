# Aspect spec: catalog-coverage

Parent PRD: `../prd.md`. **Sole aspect** — the PRD was deliberately not decomposed further:
every candidate split (seam / scenarios / refreeze) converges on the same three files
(`src/contig/data/heal_scenarios.jsonl`, `src/contig/data/heal_baseline.json`,
`tests/test_heal_scenarios.py`), so parallel aspects would contend rather than compose.
Parallelism lives inside the phases instead — see the plan's fan-out note.

## Problem slice & outcome

Four failure classes whose repair strategy is honest — `missing_reference`,
`reference_not_bgzf`, `container_pull_failed`, `download_failed` — ship live code that no
frozen scenario drives through the real `self_heal_run` loop. After this aspect each has a
frozen scenario, `heal-guard` guards it in CI, and the five classes deliberately left out
carry a stated reason at `cli.py:2681-2695`.

## In scope

- One additive `HealScenario.fasta_artifact: Literal["plain_gzip"] | None = None` field plus
  its driver wiring, enough for `reference_not_bgzf` to reach the **real**
  `_recompress_reference` (PRD R4).
- Four primary scenarios (one per class) and three give-up variants (PRD R12).
- Baseline refreeze via `--update-baseline`, with the test literals recomputed (PRD R7).
- The `heal-guard` honest-scope docstring, with a reason per not-covered class (PRD R8).
- The inert-repair finding filed as a C2 follow-up (PRD R10) and the stale trend prose
  corrected (PRD R13).

## Out of scope

Everything in the PRD's Out of Scope section — most sharply, the five inert classes, any
change to `repair.py`, and the `trace_exit` seam.

## Acceptance criteria (testable)

1. Each new scenario replays through `run_heal_scenario` with `matched is True` and the
   expected `diagnosed_class` / `actual_outcome` / `patch_applied`; detector, `propose` and
   `apply_patch` are never mocked.
2. `fasta_artifact` defaults to `None`; the nine pre-existing JSONL lines are byte-identical.
3. With `fasta_artifact="plain_gzip"`, a real non-BGZF gzip FASTA is on disk,
   `params["fasta"]` points at it, and the loop reaches
   `recompressed_reference_and_retried` through the real `_recompress_reference`.
4. `outcome_match_rate == 1.0` over the enlarged corpus; `len(covered_classes) == 11`;
   `corpus_sha == sha256_file(scenarios_path)`.
5. `uv run pytest && uv run contig eval-guard && uv run contig heal-guard` passes;
   `eval-guard` unmoved at 92.3%; detector corpora and `holdout_baseline.json` untouched.

## Dependencies & sequencing

No external dependencies. Internal order: seam → scenarios → refreeze → docstring → docs.
The refreeze must be last among code changes because it hashes the finished JSONL.

## Risks specific to this aspect

- **Needle theft** (PRD R5) is the highest-probability failure and is silent: a scenario
  classifies as another class and `outcome_match_rate` drops below the guarded 1.0.
- **The 30-minute poll** (PRD R6): a gated scenario missing both `auto_approve` and
  `poll_decision` hangs the suite for `approval_timeout=1800`.
- **`_recompress_reference` has four give-up branches** before its success path
  (`self_heal.py:783-832`); the fixture must satisfy all of them or the scenario silently
  freezes a give-up instead of the recovery it claims to test.
