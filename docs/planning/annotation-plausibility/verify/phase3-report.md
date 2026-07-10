# Phase 3 (M3) report — Rule pack + evaluator wrapper

Slug/aspect: `annotation-plausibility` / `verify` · Branch: `feat/annotation-plausibility/aliz`
Scope: Phase 3 (M3) ONLY, per `docs/planning/annotation-plausibility/verify/plan_20260710.md`.
Phase 4 (wiring into `_discover_qc` / `runner.py`) and Phase 5 (docs/changelog sync) were
NOT touched.

## Summary

Added `ANNOTATION_PLAUSIBILITY_PACK` to `src/contig/verification/rule_pack.py` (exact
contents from plan D2 — WARN-capped, no `fail_*` keys, not registered in `_RULE_PACKS`,
imported directly like the other plausibility packs) and
`evaluate_annotation_plausibility(vcf_path, label="sample") -> list[QCResult]` to
`src/contig/verification/annotation_plausibility.py`, mirroring
`somatic_plausibility.evaluate_somatic_plausibility`'s shape: build `by_metric`, filter to
`computable`, run the shared `evaluate()`, then an explicit loop that appends an
`unverified` `QCResult` (value `None`, `kind="metric"`) for each rule whose metric is
`None` — the never-a-false-pass guarantee, since the shared `evaluate()` silently skips
absent metrics.

## Files modified

- `src/contig/verification/rule_pack.py` — added `ANNOTATION_PLAUSIBILITY_PACK` next to
  `SOMATIC_PLAUSIBILITY_PACK`, unregistered in `_RULE_PACKS`.
- `src/contig/verification/annotation_plausibility.py` — added
  `evaluate_annotation_plausibility`; imports `QCResult`,
  `ANNOTATION_PLAUSIBILITY_PACK`, `evaluate`.
- `tests/verification/test_annotation_plausibility.py` — added the evaluator test block
  (in-band pass, out-of-band warn-never-fail, uncomputable-unverified, check-name/label
  assertions).

## Optional cleanup done

Replaced the module-local `_has_key` (duplicate logic) with an import of
`annotation_structural._record_has_key`, updating both call sites and the module
docstring. Verified trivially safe: identical body, no behavior change, full suite still
green.

## TDD evidence

RED: `uv run pytest tests/verification/test_annotation_plausibility.py` failed at
collection (`ImportError: cannot import name 'evaluate_annotation_plausibility'`) before
any implementation — confirmed the new tests exercise code that didn't exist yet.

GREEN: after adding the rule pack and evaluator,
`uv run pytest tests/verification/test_annotation_plausibility.py tests/verification/test_rule_pack.py -q`
→ 84 passed.

Full suite: `uv run pytest -q` → all green (no regressions; nothing in
`src/contig/data/*baseline*` or corpus files touched).

## Design notes / deviations from the plan

- None. `ANNOTATION_PLAUSIBILITY_PACK` contents are byte-for-byte the plan's D2 snippet
  (message strings reconstructed via string concatenation for line length, semantically
  identical). `evaluate_annotation_plausibility`'s signature, `by_metric`/`computable`
  construction, and the explicit unverified loop follow
  `somatic_plausibility.evaluate_somatic_plausibility` exactly, except there is no
  header-derived label fallback (the plan's signature is `label="sample"`, not a
  `sample=None` override with header sniffing) — annotation plausibility has no analogous
  "tumor sample name" concept to sniff, so a plain default is correct here and was
  confirmed against the plan text.

## Commit

`91242af` — `feat(verify): annotation plausibility rule pack + evaluator [C7 M3]`
