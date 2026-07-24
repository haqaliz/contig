"""Deterministic paper-claim extractor core (aspect `extractor-core` of
reproduce-paper-claims).

Turns a paper's text into a list of candidate numeric claims -- the pure,
stdlib-only heart of `contig extract-claims`. `extract_claims` targets
**named-metric + number** shapes only (a metric word from a curated vocabulary
joined to a number by a connective, e.g. `AUC of 0.91`) and is deliberately
conservative: it prefers precision over recall, records provenance (the source
sentence, the `%` unit) for a human to review, and **never raises** -- any
malformed / empty / non-str input, or any per-candidate parse issue, degrades
to skipping that candidate (mirroring the never-raises resolvers in
`verification/reproduce.py`).

The output is a draft for review, never a verified result: an ExtractedClaim
carries no locator, so at reproduce time an unreviewed claim degrades to
UNVERIFIED -- extraction can never manufacture a false REPRODUCED.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class ExtractedClaim:
    """One candidate numeric claim pulled from paper text.

    `id` is a deterministic, human-editable slug of `metric`, uniquified within
    the extraction (`auc`, `auc_2`, ...). `value` is the parsed number (for a
    percentage, the RAW number -- `87` from "87%", never `0.87`). `tolerance`
    is the reproduce default (`0.1`). `metric` is the matched metric word as it
    appeared in the text; `unit` is `"%"` for a percentage else `None`.
    `source_text` is the sentence the value was found in (provenance for the
    review sidecar). `origin` is `"heuristic"` here; the optional LLM assist
    (aspect `llm-assist`) sets `"llm"`.
    """

    id: str
    value: float
    tolerance: float = 0.1
    metric: str
    unit: str | None = None
    source_text: str = ""
    origin: str = "heuristic"


# Placeholder constant + slug helper; fleshed out in Phase 2. Kept here so the
# module's public surface (`ExtractedClaim`, `extract_claims`, `_slug`,
# `_METRIC_VOCAB`) is importable from the start.
_METRIC_VOCAB: tuple[str, ...] = ()


def _slug(metric: str) -> str:
    """Deterministic id slug of a metric word. Filled in in Phase 2."""
    return metric


def extract_claims(text: str) -> list[ExtractedClaim]:
    """Extract candidate named-metric numeric claims from `text`. Never raises."""
    return []
