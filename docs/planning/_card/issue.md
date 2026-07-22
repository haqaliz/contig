# Card: feat reproduce-freshness-guard (C8, follow-on to slice 5)

**Type:** feat · **Owner:** aliz · **Branch:** `feat/reproduce-freshness-guard/aliz`

No GitHub issue — this unit of work came from `/contig-next` (cn), 2026-07-23. The
recommendation below is the source brief.

## Brief

Extend the `contig reproduce` mtime freshness guard — today live only in the notebook
(`.ipynb`) locator branch (`src/contig/verification/reproduce.py:1061-1103`,
`run_started_at` threaded at `:847`) — to the JSON (slice 1.5), TSV/CSV table (slice 3),
and file-mode pattern (slice 4) locators, so a claim can never bind to an artifact the
run did not rewrite.

This is the slice `docs/planning/reproduce-notebook-locator/prd.md:202-215` (R2)
explicitly deferred as "its own slice": a committed `results.json` or `de.tsv`
reproduces just as falsely as a committed notebook.

**Caveat the dig must decide, not assume:** this changes shipped behavior (a repo whose
`--run` doesn't rewrite the located file flips `REPRODUCED` → `UNVERIFIED`) — choose
guard-on-by-default vs. an opt-out flag, and confirm the `pattern`-without-`from` stdout
mode is exempt by construction.

**Constraints:** keep R1 unchanged (no fudge tolerance), stdlib-only, no `models.py`
change if avoidable, test-first with `os.utime` fixtures and scripted executors, no real
repo or network in CI.

## Why (from the /contig-next ranking)

- Closes a live false-`REPRODUCED` class in already-shipped code, not a new feature.
- Directly on the moat: "make every verdict harder to fool"
  (`docs/technical/CAPABILITY_ROADMAP.md:1325`). C8's pitch — "I ran 50 published papers'
  code, here's how many reproduced" (`:1270-1274`) — is only credible if the count isn't
  inflated by artifacts the authors committed.
- Unblocked and small: the mechanism exists and is tested; this generalizes a
  `stat().st_mtime >= run_started_at` check that today lives only in the notebook branch.
  Contrast the standing C8 list: paper-parsing needs a PDF dependency (the stdlib-only
  contract is what already hard-blocks figures, `CAPABILITY_ROADMAP.md:1256-1263`); remote
  `<doi|url>` needs network + DOI resolution.

## Named prior art / constraints to honor

- **R1 (accepted, do not "fix"):** coarse-mtime filesystems can yield a false `UNVERIFIED`.
  No fudge tolerance — "a tolerance is exactly the size of the hole it opens"
  (`reproduce-notebook-locator/prd.md:202-208`).
- **R1a (honest limit):** the guard proves *rewritten*, not *recomputed*.
- **R2 (this slice):** guard scope is deliberately inconsistent today; widening it changes
  shipped behavior and belongs in its own slice.

## Alternates considered and rejected for now

- Remote `<doi|url>` intake (network + clone safety surface).
- C6 fold-in of C1/C3 signals — genuinely blocked on a labeling design
  (`CAPABILITY_ROADMAP.md:1029`, `:908-910`).
