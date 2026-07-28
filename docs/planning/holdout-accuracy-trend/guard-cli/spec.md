# Aspect spec: guard-cli

Parent PRD: `../prd.md`. Aspect 2 of 3. **Depends on `history-store`.**

## Problem slice & outcome

Give `contig eval-guard` and `contig heal-guard` the `--snapshot` / `--history`
surface that `eval-detector` already has, plus a per-version delta in the `--history`
render, plus append-on-`--update-baseline`, plus the release-time accrual hook. CI stays
bare. After this aspect, a founder can record and read the held-out and heal trends from
the CLI.

## In scope

- **R3/R6:** on **both** guards, add `--snapshot`, `--history`, `--history-file`.
  - `--snapshot`: append one snapshot (the same object the guard already builds) to the
    respective history file, **in addition to** guarding (guard comparison + exit code
    unchanged).
  - `--history`: load + render the trend oldest→newest with a **per-version delta column**
    (Δ vs previous point; first row `—`; latest row marked `←latest`), then return without
    re-evaluating. `--json` prints the snapshot array. Empty/absent → honest one-line note.
  - `--history-file`: override path (for tests/fixtures), mirroring
    `eval-detector --history-file`.
- **R5/R6:** on `--update-baseline`, after `save_baseline`/`save_heal_baseline`, also
  `append_jsonl(snapshot, history_path)` — one object, written to both baseline and history.
- **R7:** CI (`.github/workflows/ci.yml:23,27`) stays bare — **no** `--snapshot` added there.
- **R10:** add a documented step to `RELEASING.md`'s "Cut a release" running
  `contig eval-guard --snapshot` + `contig heal-guard --snapshot` and committing the updated
  history files with the version bump.

## Out of scope

- The persistence primitive + seeds (aspect `history-store`).
- Dashboard (aspect `dashboard-trend`).
- Any change to guard thresholds, pass/fail, exit codes, or baseline values. `--history`
  and `--snapshot` never change the guard verdict; a bare guard is byte-for-byte as today.

## Acceptance criteria (testable, via `CliRunner`)

For **each** guard (`eval-guard` over `EvalSnapshot`/holdout, `heal-guard` over
`HealSnapshot`/heal), using `--history-file`/`--baseline`/`--holdout`|`--scenarios` pointed
at `tmp_path`:

1. **Bare command writes nothing** — invoke with no `--snapshot`/`--update-baseline`; the
   history file is unchanged (or still absent). Guard output/exit unchanged from today.
2. **`--snapshot` appends exactly one** line and still runs the guard (exit code matches the
   no-snapshot guard for the same inputs).
3. **`--update-baseline` refreezes AND appends one** history line (baseline file written +
   history grew by one).
4. **`--history` renders** the points oldest→newest with the metric, a delta column (first
   `—`, subsequent `+X.Xpp`), and `←latest` on the last; exits 0; does not re-evaluate.
5. **`--history` empty** (absent/empty file) prints the honest note, exits 0.
6. **`--history --json`** prints a JSON array of the snapshots.
7. `RELEASING.md` contains the two `--snapshot` commands in the cut-a-release steps.
8. Full suite green (`uv run pytest`).

## Dependencies & sequencing

Inbound: `history-store` (needs `append_jsonl`, `load_jsonl`,
`default_holdout_history_path`, `default_heal_history_path`). Independent of
`dashboard-trend` — the two can run in parallel after `history-store`.

## Open questions / risks

- Heal `--history` "recovery H/T": `HealSnapshot` stores `recovery_rate` + `scenario_count`,
  not the healed count → render `recovery {round(rate*n)}/{n}`. Informational only; the
  delta headline is on `outcome_match_rate` (matches the guard's "recovery reported, never
  guarded" honesty).
