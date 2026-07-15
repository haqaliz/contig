# Aspect spec: duplication-metric

Parent PRD: [`../prd.md`](../prd.md) (approved 2026-07-15).

## Problem slice

`RNASEQ_PLAUSIBILITY_PACK`'s `duplication_rate` check has never produced a value on a real
`nf-core/rnaseq` run. The metric is present in MultiQC's general-stats — Contig asks for it under
the wrong key case (`percent_duplication` vs MultiQC's `PERCENT_DUPLICATION`) and declares the
wrong unit (0–100 vs the raw 0–1 fraction actually stored).

This aspect makes that one metric arrive, correctly, as an **informational-only** result.

## User outcome

A bulk RNA-seq run's verdict reports a real library-complexity number (e.g. `0.707`), attributed
to Picard via MultiQC, with Contig explicitly declining to judge it. Today the same run reports
`duplication_rate: unverified` and carries no signal.

## In scope

- M1 key fix, M2 scale fix (**same commit** — M1 alone is a false pass)
- M3 informational-only (no band)
- M4 `_expected_range` support for band-less rules (shared machinery)
- M5 the `[0.0, 1.0]` assumption guard
- M6 re-point the fabricated tests
- M7/M8 the misleading comments + per-metric unit documentation
- M9 correct `CAPABILITY_ROADMAP.md` + `CHANGELOG.md`

## Out of scope

`rrna_contamination` (stays a guessed slug — recorded debt); FAIL/WARN severity; the
`runner.py:412` `multiqc is not None` gate bug; **any change to `qc_ingest.py`**.

## Acceptance

See the PRD's Acceptance section (11 criteria). Headline: `0.96` → `status="pass"`,
`value == 0.96`; no input produces WARN/FAIL; `95.0` → `unverified` (guard); the old key shape →
`unverified` (regression lock); `expected_range` never renders `">= None"`.

## Dependencies / sequencing

M4 must land **before** M3 creates the repo's first band-less rule, or that rule renders
`expected_range=">= None"`.

## Open questions resolved here

**Rename `duplication_rate` → `duplication_fraction`?** **No.** See the plan's Decision D1.
