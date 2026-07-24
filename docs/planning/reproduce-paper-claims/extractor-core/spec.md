# Aspect spec: extractor-core

Parent PRD: `../prd.md`. Aspect 1 of 3. Foundation — no dependencies.

## Problem slice & user outcome

The pure, deterministic, stdlib-only heart of paper-claim extraction: turn paper text into a
list of candidate numeric claims, honestly and without ever raising. Everything else
(`llm-assist`, `cli-command`) composes on top of this.

## In scope

- **Module** `src/contig/verification/claim_extraction.py`, stdlib-only (`re`), **never raises**.
- **`ExtractedClaim`** (frozen dataclass): `id: str`, `value: float`, `tolerance: float`
  (default `0.1`), `metric: str` (the matched metric word), `unit: str | None` (`"%"` or `None`),
  `source_text: str` (the sentence/snippet the value was found in), `origin: str`
  (`"heuristic"` here; `"llm"` set by the `llm-assist` aspect).
- **`extract_claims(text: str) -> list[ExtractedClaim]`** — deterministic:
  - Targets **named-metric + number** only. A match is a metric word from the vocabulary,
    joined to a number by a connective, e.g. `AUC of 0.91`, `accuracy of 87%`, `F1 = 0.83`,
    `log2 fold change of -2.3`, `Pearson correlation of 0.76`.
  - **v1 metric vocabulary (conservative, extensible seed — a module constant):** `auc`,
    `auroc`, `auprc`, `area under the curve`, `accuracy`, `precision`, `recall`, `f1`,
    `f1 score`, `f-score`, `sensitivity`, `specificity`, `pearson`, `spearman`, `correlation`,
    `r2`, `r²`, `r-squared`, `mse`, `rmse`, `mae`, `dice`, `iou`, `fold change`,
    `log2 fold change`, `log fold change`. Case-insensitive. This membership is the
    precision/recall lever (resolves PRD 🟡 #3) — deliberately small; grow only with evidence.
  - **Connectives:** `of`, `was`, `is`, `=`, `:`, `reached`, `achieved`, `at` (between the
    metric and the number, allowing intervening words like "an", "a", "was", within a small
    token/character window).
  - **Number:** signed decimal, optional `%`, optional scientific notation
    (`-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?%?`). Parsed via `float()` (strip a trailing `%` first);
    non-finite (`inf`/`nan`) skipped.
  - **Percentages:** if `%` is present, `value` = the bare number (`87` from `87%`), `unit =
    "%"`, and it is **never divided by 100** — the repo output could be `87` or `0.87`, so the
    human reconciles it via the sidecar. Resolves PRD 🟡 #2 (unit half).
  - **Inequalities skipped:** if the number is immediately preceded (after connective/whitespace
    trim) by `<`, `>`, `≤`, `≥`, `<=`, `>=`, skip it — an inequality is not a point value.
  - **id generation:** deterministic slug of the metric word (lowercase, non-alphanumeric → `_`,
    collapsed) uniquified within the file (`auc`, `auc_2`, `auc_3`, …). No randomness (must be
    reproducible). Human-editable.
  - **De-dup:** key = **`(metric_slug, value)`**, collapsing duplicates **file-wide regardless
    of section** (section is not tracked in v1); the first occurrence's `source_text` is kept.
    This is the deliberate answer to the review-gate de-dup question.
  - **Ordering:** first-appearance order, so output is stable/diffable.
  - Malformed / empty / non-str input → `[]`. Any internal parse issue degrades to skipping that
    candidate, never an exception.

## Out of scope (this aspect)

- The LLM assist (aspect `llm-assist`), all file/CLI I/O and the sidecar (aspect `cli-command`).
- Locator inference, PDF/DOI, markdown-table parsing, inequalities-as-claims.

## Acceptance criteria (test-first)

Resolves PRD 🟡 #1 (measurable recall) with a **committed labeled fixture corpus**:

- **Fixture corpus:** 3–5 short paper-excerpt `.md`/`.txt` strings (inline or `tests/fixtures/`)
  each paired with a hand-labeled expected set of `(metric_slug, value, unit)` tuples.
  *Bar:* the core extracts **every labeled named-metric claim** in the fixtures and emits
  **zero malformed** entries (every emitted claim has a finite float value and a non-empty id).
- A percentage fixture (`accuracy of 87%`) → `value == 87.0`, `unit == "%"`, not `0.87`.
- An inequality fixture (`p < 0.001`) → **no** claim emitted.
- A duplicate fixture (same metric+value twice) → **one** claim; `source_text` = first hit.
- Distinct metrics sharing a value → two claims with distinct ids.
- id determinism: extracting the same text twice yields byte-identical ids.
- Robustness: empty string, non-str, and a wall of prose with no metrics all → `[]`, never raise
  (a "wild inputs never raise" test in the `test_reproduce_locator.py` style).

## Dependencies & sequencing

None. Build first; `llm-assist` and `cli-command` import `ExtractedClaim` + `extract_claims`.

## Open questions / risks

- Connective window width (how many tokens between metric and number) — start tight (≤ ~4
  tokens / ~40 chars), widen only if fixtures show misses. Over-wide = prose noise.
- `r`/`correlation` alone are common English words; the vocabulary uses the multi-word forms
  (`pearson`/`spearman`/`correlation`) to limit false positives — revisit if recall suffers.
