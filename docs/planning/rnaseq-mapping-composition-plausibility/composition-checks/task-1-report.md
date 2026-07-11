# Task 1 report — RSeQC read_distribution parser (Phase 1 + Phase 4)

Branch: `feat/rnaseq-mapping-composition-plausibility/aliz`
Scope: **only** Phase 1 (parser) and Phase 4 (committed fixture) of
`docs/planning/rnaseq-mapping-composition-plausibility/composition-checks/plan_20260711.md`.
`rule_pack.py` and `runner.py` were **not** touched (Phases 2/3, other tasks).

## What was created

1. **`src/contig/verification/rnaseq_metrics.py`** — new, stdlib-only module.
   - `parse_read_distribution(path) -> dict[str, float]`: pure function, reads
     only the passed file. Parses the RSeQC preamble (`Total Reads`,
     `Total Tags`, `Total Assigned Tags`) and the `Group` table
     (`CDS_Exons`, `5'UTR_Exons`, `3'UTR_Exons`, `Introns`; the
     `TSS_up_*kb`/`TES_down_*kb` windows are read but never summed into any
     metric — they double-count with the exon/intron rows).
   - Exports `EXONIC_FRACTION`, `INTRONIC_FRACTION`, `UNASSIGNED_FRACTION`
     slug constants, matching the plan's locked names.
   - Implemented the plan's Phase 1 skeleton essentially verbatim (split
     `_to_float`/`_trailing_number` as two small helpers, matching the
     methylseq module's style of a shared `_to_float`).
   - Denominators are commented as intentional in both the module docstring
     and inline at each computation site, per the plan's explicit ask
     ("Keep the 'denominators are intentional' comments — they are
     load-bearing").
   - Omit-never-guess: exonic/intronic omitted when `Total Assigned Tags` is
     absent, non-numeric, or `<= 0`; unassigned omitted when `Total Tags` is
     absent/`<=0`, or when `Total Assigned Tags` is absent, or when
     `total_tags - assigned` would be negative. Garbage/empty/rule-lines-only
     input returns `{}`.

2. **`tests/fixtures/rnaseq/WT_REP1.read_distribution.txt`** — committed
   fixture, copied verbatim (values and RSeQC layout unchanged) from the real
   run artifact at
   `/Users/aliz/dev/at/contig/runs/testpass2/results/star_salmon/rseqc/read_distribution/WT_REP1.read_distribution.txt`
   (healthy yeast test profile). Only whitespace-only trailing padding on the
   `Group` header line was trimmed; all data values are untouched.

3. **`tests/verification/test_rnaseq_metrics.py`** — new test module,
   mirroring the `_FIXTURES_DIR` + inline-triple-quoted-string + local
   `_write(tmp_path, name, text)` pattern from
   `tests/verification/test_methylseq_metrics.py` /
   `tests/verification/test_ampliseq_metrics.py`. Covers:
   - Healthy fixture via `_FIXTURES_DIR` → exact fractions via
     `pytest.approx` (computed from the same integers in the fixture:
     `129779/129802`, `23/129802`, `(146154-129802)/146154`), confirming the
     plan's ≈0.9998 / ≈0.00018 / ≈0.1119 figures.
   - Low-exonic / high-intronic synthetic (small `CDS_Exons`, large
     `Introns`) → exonic < 0.50, intronic > 0.30.
   - High-unassigned synthetic (`Total Assigned Tags` ≪ `Total Tags`) →
     unassigned > 0.30.
   - Omit-never-guess edges: missing `Total Assigned Tags` line (exonic,
     intronic, **and** unassigned all omitted — see decision note below);
     missing `Introns` row (intronic omitted, exonic/unassigned present);
     `Total Assigned Tags: 0` (exonic/intronic omitted, no ZeroDivision);
     `Total Tags: 0` (unassigned omitted).
   - Garbage file, empty file, and a file with only `====` rule lines → all
     return `{}`.
   - Determinism: same input parsed twice → identical dict.

## Test commands run

```
uv run pytest tests/verification/test_rnaseq_metrics.py -q
```
→ `11 passed` (all green on first implementation; no RED→fix iteration was
needed beyond the initial expected "module not found" RED, confirmed before
writing the implementation).

```
uv run pytest
```
→ `1463 passed, 1 skipped in 11.95s`
(baseline was `1452 passed, 1 skipped`; this task adds 11 new tests, 0
regressions, skip count unchanged.)

## Edge-case decision worth flagging

The plan's Phase 1 RED-step bullet list says: *"a file missing the `Total
Assigned Tags` line → exonic & intronic omitted, **unassigned still computed
if `Total Tags` present**"*. The plan's own Phase 1 GREEN code skeleton (which
I implemented verbatim) computes `unassigned_fraction` only when
`total_tags is not None and total_tags > 0 and assigned is not None` — i.e.
it also requires `assigned` to be present, because the locked formula is
`(Total Tags − Total Assigned Tags) / Total Tags`, which needs both operands.
With `assigned` fully absent (not just zero), there is no non-guessed way to
compute `Total Tags − Total Assigned Tags`.

I treated the **locked formula + explicit code skeleton** as authoritative
over the prose bullet (which reads as an imprecise summary, not a
independent requirement — the task brief told me to use the plan's exact
code/values verbatim). My test
`test_missing_total_assigned_tags_omits_exonic_and_intronic_only` asserts all
three slugs are omitted in that case, matching the shipped implementation and
the "omit-never-guess" principle stated as a hard constraint in this task's
brief. Flagging this explicitly in case the Phase 2/3 implementer or a
reviewer expected the prose bullet's behavior instead.

## Other notes

- No changes to `rule_pack.py` or `runner.py` (out of scope, verified via
  `git status` before and after — only the three new files above plus this
  report were added).
- No new dependencies; `parse_read_distribution` reads only the path it is
  given (no globbing, no cwd assumptions, no network).
- Pre-existing worktree modifications to `docs/planning/_card/issue.md`,
  `docs/planning/_card/understanding.md`, and `uv.lock` were present before
  this task started and are unrelated to this change; left untouched and not
  included in this task's commits.
