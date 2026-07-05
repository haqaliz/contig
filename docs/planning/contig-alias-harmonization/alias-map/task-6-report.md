# Task 6 report — docs sync + dead-code sweep (Phase 6, final)

Branch: `feat/contig-alias-harmonization/aliz`

## Files touched

- `CHANGELOG.md` — new entry under `## [Unreleased]` for the per-contig alias
  harmonization feature (C2 follow-on of v0.9.0's chr-prefix GTF harmonizer).
- `docs/technical/CAPABILITY_ROADMAP.md` — C2 section: added a "Shipped (per-contig
  alias harmonization slice — Unreleased)" paragraph; moved "per-contig name mapping
  (e.g., `chrM`↔`MT`)" out of the C2 deferred list (replaced with "exhaustive
  per-assembly alias-table completeness beyond the GRCh38 seed", which remains
  genuinely deferred); updated the C2 row of the Sequencing summary table to note
  the shipped slice.
- `FEATURES.md` — C2 row: window column and description column both updated to
  mention the per-contig alias harmonization slice, mirroring the CHANGELOG/roadmap
  wording; "per-contig name mapping" dropped from the still-deferred tail, replaced
  with "exhaustive per-assembly alias-table completeness".
- `docs/planning/self-heal-reference-mismatch/understanding.md` — appended an
  "Update — RESOLVED" section at the end (file otherwise untouched) noting that the
  `MT`/`chrM` per-contig alias edge case flagged in open question 4 is now resolved
  by this feature, referencing the branch and the resolving module
  (`src/contig/reference_harmonize.py`) and table
  (`src/contig/data/contig_aliases.tsv`). Scaffold contigs beyond the GRCh38 seed
  are noted as still deferred, not resolved.
- `src/contig/reference_harmonize.py` — removed the dead
  `HarmonizationDirection = Literal["add_chr", "strip_chr"]` type alias and the now
  otherwise-unused `Literal` import (the `HarmonizationPlan.direction` field is
  typed as plain `str` and carries `"add_chr" | "strip_chr" | "alias"`; nothing in
  `src/` or `tests/` referenced the alias itself).

## CHANGELOG entry summary

One `### Added` bullet under `## [Unreleased]`, mirroring the v0.9.0 entry's tone:
widened harmonizer as a general per-contig rename map driven by a FASTA-set lookup;
universal `M`↔`MT` mito alias (code constant) + curated extensible GRCh38 scaffold
table (`contig_aliases.tsv`, sourced from UCSC chromAlias, loader fails loud on
malformed/duplicate rows); resolves the UCSC/Ensembl mito case, the
autosomes-already-match-but-mito-differs residual case (previously silently
skipped), pure-alias mismatches, and hybrid FASTA (`chrMT`) via FASTA lookup;
refuses genuine wrong-assembly and non-injective rename maps; CLI pre-flight now
plan-driven with a strengthened overlap-increase post-check; `--allow-reference-
mismatch` and `rerun`/`resume` behavior unchanged; WARN breadcrumb now enumerates
unmatched contigs; provenance-only eval capture (no new `FailureClass`/corpus case,
matching v0.9.0); deferred items listed (exhaustive per-assembly completeness,
chromAlias network fetch, FASTA rewriting, assembly-signature comparison). No
version bump, no git tag — left for the separate release step.

## Dead-code sweep confirmation

`grep -rn "HarmonizationDirection" src/ tests/` before removal found exactly one
hit: the definition itself at `src/contig/reference_harmonize.py:26`. No other
reference in `src/` or `tests/` (matches in `docs/planning/**` are historical
plan/report artifacts from earlier phases and were left untouched, per the task
scope of "nothing else"). Confirmed dead; removed along with the now-unused
`Literal` import. Post-removal grep of `src/` and `tests/` is clean (no hits).

## Suite result

`uv run pytest` (full suite, after the dead-code removal): **1124 passed, 1
skipped** — matches the expected baseline exactly. No behavior changes were made
(docs-only + a type-alias removal).
