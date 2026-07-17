# Aspect spec: history-store

Parent PRD: `../prd.md`. Aspect 1 of 3. **Foundation — aspects `guard-cli` and
`dashboard-trend` depend on this.**

## Problem slice & outcome

The two guards produce a snapshot object (`EvalSnapshot` / `HealSnapshot`) but there is
nowhere to accumulate them over time. This aspect adds the **persistence primitive**: a
generic append-only JSONL store parametrized by the pydantic model, default paths for the
two new committed history files, and the two files seeded with one point each. After this
aspect, `append`/`load` of both snapshot types round-trips; no CLI/dashboard yet.

## In scope

- **R1/R2 (PRD):** a generic `append_jsonl(snapshot, path)` / `load_jsonl(model_cls, path)`
  in a new `src/contig/snapshot_history.py`, mirroring `eval_history.py:49-66` but
  parametrized by the pydantic class. `load_jsonl` skips **blank AND malformed** lines
  (strictly more tolerant than the shipped `load_history`, which only skips blank — it
  matches the dashboard reader `runs.ts:getEvalHistory`). Missing file → `[]`.
- `default_holdout_history_path()` in `holdout.py` → `data/holdout_history.jsonl`;
  `default_heal_history_path()` in `heal.py` → `data/heal_history.jsonl` (siblings of the
  existing `default_*_path` helpers).
- Two committed seed files, one line each, each line being the current committed baseline
  re-serialized as the matching snapshot: `holdout_history.jsonl` ← the `EvalSnapshot` in
  `holdout_baseline.json`; `heal_history.jsonl` ← the `HealSnapshot` in `heal_baseline.json`.

## Out of scope

- Any CLI wiring (`--snapshot`/`--history`) — aspect `guard-cli`.
- Any dashboard reader/component — aspect `dashboard-trend`.
- New models (reuse `EvalSnapshot` / `HealSnapshot` verbatim).
- Touching `eval_history.py` / `eval_history.jsonl` (the training-corpus trend is untouched;
  optionally the existing `append_snapshot`/`load_history` could later delegate to the
  generic helpers, but that refactor is **not** required here).

## Acceptance criteria (testable)

1. `append_jsonl` creates parent dirs, appends exactly one JSON line per call; two appends →
   two lines.
2. `load_jsonl(EvalSnapshot, p)` and `load_jsonl(HealSnapshot, p)` round-trip appended
   snapshots; a missing path → `[]`.
3. `load_jsonl` skips a blank line and a malformed (`not json`) line without raising, and
   returns the valid remainder.
4. Each seeded file exists, has **exactly one** line, parses to the right snapshot type, and
   its content **equals** the current committed baseline (same `accuracy` /
   `outcome_match_rate`, `corpus_sha`, `contig_version`).
5. Full suite stays green (`uv run pytest`), baseline 1601 passed / 1 skipped.

## Dependencies & sequencing

None inbound. Blocks `guard-cli` and `dashboard-trend`. Do first.

## Open questions / risks

- Seeds are generated from the baselines, so they inherit the baselines' (older)
  `contig_version` (`0.22.0` / `0.21.0`) and `timestamp`. Accepted — the seed honestly
  records the baseline it was frozen from; new release points carry the current version.
