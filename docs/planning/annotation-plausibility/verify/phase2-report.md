# Phase 2 (M3) report — CSQ/ANN consequence parser + plausibility metrics

Slug/aspect: `annotation-plausibility` / `verify` · Branch: `feat/annotation-plausibility/aliz`
Scope: Phase 2 (M3) ONLY, per `docs/planning/annotation-plausibility/verify/plan_20260710.md`.
Phase 3 (rule pack + evaluator), Phase 4 (wiring into `_discover_qc`), and Phase 5
(docs/changelog) were NOT touched. No files from Phase 1 (`registry.py`, `runner.py`,
`self_heal.py`) were touched.

## Summary

New module `src/contig/verification/annotation_plausibility.py` computes two
deterministic metrics from a VEP `CSQ`- or SnpEff `ANN`-annotated VCF:
`real_consequence_fraction` and `intergenic_fraction`, over the set of records
that carry the resolved annotation field ("annotated"). No rule pack, no
`QCResult` evaluator, no wiring — pure metrics, as scoped.

## Files added

- `src/contig/verification/annotation_plausibility.py`
- `tests/verification/test_annotation_plausibility.py`

## API surface

- `_SEVERITY_ORDER` / `_SEVERITY_RANK` / `_UNKNOWN_RANK = 1` — copied verbatim
  from the plan's D1 pinned decision (23-term least→most-severe SO ordering;
  `intergenic_variant` is the unique rank 0).
- `_ANN_CONSEQUENCE_INDEX = 1` — SnpEff's fixed `Allele|Annotation|...` layout;
  never header-resolved (unlike CSQ).
- `_consequence_index_csq(header_lines) -> int | None` — parses the
  `##INFO=<ID=CSQ,...Format: ...>` header line, splits the `Format:` string on
  `|`, returns the index of `Consequence`, else `None` (no CSQ line, or the
  Format string has no `Consequence` subfield).
- `_has_key(info, key) -> bool` — local presence check (`KEY=` token in the
  INFO column); a private per-module copy of `annotation_structural`'s
  `_record_has_key`, per the codebase's "no shared VCF abstraction" convention.
- `_variant_terms(info_value, key, cons_index) -> list[str]` — pulls `KEY=...`,
  splits entries on `,` (one per transcript), takes each entry's subfield at
  `cons_index`, splits on `&`, returns lowercased non-empty terms. Returns `[]`
  both when the key is absent and when every entry's subfield is empty — the
  caller (main loop) distinguishes "field absent" (not counted as annotated)
  from "field present, no parseable term" (counted as annotated + empty) by
  checking `_has_key` separately before calling this.
- `_most_severe_rank(terms) -> int | None` — `None` for `[]`, else
  `max(_SEVERITY_RANK.get(t, _UNKNOWN_RANK) for t in terms)`.
- `AnnotationPlausibilityMetrics` (frozen dataclass) — `real_consequence_fraction:
  float | None`, `intergenic_fraction: float | None`.
- `annotation_plausibility_metrics(vcf_path) -> AnnotationPlausibilityMetrics` —
  single streaming pass (gzip-transparent via reused `_open_text`); resolves
  the key via reused `_declared_key`, else sniffs the first data record that
  carries `CSQ` or `ANN`; for `CSQ` also resolves the consequence index and
  returns the all-`None` sentinel immediately if that fails; tallies
  real/intergenic over annotated records; `annotated == 0` → all-`None`.

Reused (not reinvented) from `annotation_structural.py`: `_open_text`,
`_declared_key`. No shared VCF abstraction was added, per `somatic_plausibility.py:20-23`'s
established convention of per-module readers.

## Test cases (`tests/verification/test_annotation_plausibility.py`, 13 tests)

Unit:
1. `_most_severe_rank([])` → `None`.
2. `_most_severe_rank(["missense_variant"])` → its rank.
3. `_most_severe_rank(["intergenic_variant", "some_brand_new_term"])` →
   `_UNKNOWN_RANK` (1), which is `>` intergenic's rank 0 — an unknown term is
   never misclassified as intergenic.
4. `_most_severe_rank` picks the max across several known terms.
5. `_consequence_index_csq` on a well-formed VEP header → `1`.
6. `_consequence_index_csq` on a CSQ header whose `Format:` omits `Consequence`
   → `None`.
7. `_consequence_index_csq` on a header with no CSQ line at all (ANN header)
   → `None`.

Metrics (`annotation_plausibility_metrics`):
8. VEP `CSQ`, multi-transcript, comma-separated entries, one `&`-joined —
   3 annotated records (1 real via `&`-joined missense+splice_region, 1
   intergenic, 1 real via intron_variant) → `real_consequence_fraction ==
   2/3`, `intergenic_fraction == 1/3`.
9. SnpEff `ANN` (fixed index 1), gzipped — 1 real (`stop_gained`), 1
   intergenic → `0.5` / `0.5`.
10. All `intergenic_variant` → `intergenic_fraction == 1.0`,
    `real_consequence_fraction == 0.0`.
11. Field-present-but-empty-Consequence record alongside one real record →
    counts as *empty* (`real_fraction == 0.5`, `intergenic_fraction == 0.0`,
    NOT counted as intergenic).
12. Unresolvable CSQ `Format:` (no `Consequence` subfield declared) → both
    metrics `None`.
13. No record carries the annotation field at all → both metrics `None`.

## Edge-case decisions

- **"Empty" vs "absent" disambiguation**: `_variant_terms` alone cannot tell
  these apart (both return `[]`). The main loop resolves this by checking
  `_has_key(info, key)` before incrementing `annotated` — only records that
  *carry* the field are tallied at all; among those, an empty parse lowers
  `real_consequence_fraction` (fewer "real" numerator) without touching
  `intergenic_fraction`'s numerator, matching D1/D2 exactly.
- **CSQ index failure returns immediately**: per the plan, an unresolvable CSQ
  `Format:` short-circuits to the all-`None` sentinel as soon as it is
  detected (at header resolution, or at first-sniffed-record resolution) —
  it does not fall through to tally anything first, since any tally would be
  built on a guessed index.
- **Sniffing an undeclared key still requires CSQ index resolution**: if the
  header declares no CSQ/ANN INFO line at all but a data record's INFO
  carries a `CSQ=` token, the key is sniffed as `CSQ`, but
  `_consequence_index_csq` will also return `None` (no header line to parse),
  so this degrades to `None`/`None` too — never a guessed index from a
  header-stripped file.
- **Header lines are collected in full before the first data line**, matching
  real VCF structure (all `##`/`#CHROM` lines precede all data lines), so by
  the time any per-record resolution runs, `header_lines` already holds the
  complete header.

## Validation

- `uv run pytest tests/verification/test_annotation_plausibility.py -q` → 13
  passed.
- `uv run pytest -q` → full suite green, no regressions (only new files added;
  `registry.py`/`runner.py`/`self_heal.py`/`rule_pack.py` untouched).
