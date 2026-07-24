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

import json
import math
import os
import re
from dataclasses import dataclass

from contig import detect

_DEFAULT_TOLERANCE = 0.1


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
    tolerance: float = _DEFAULT_TOLERANCE
    metric: str
    unit: str | None = None
    source_text: str = ""
    origin: str = "heuristic"


# v1 metric vocabulary (conservative, extensible seed). Case-insensitive; the
# membership here is the precision/recall lever -- deliberately small, grow only
# with evidence. `r`/`correlation`-alone are avoided in favor of the multi-word
# forms (`pearson`/`spearman`/`correlation`) to limit false positives on common
# English words. Order does not matter (the match regex sorts by length so the
# longest phrase wins at a position, e.g. "log2 fold change" over "fold change").
_METRIC_VOCAB: tuple[str, ...] = (
    "auc",
    "auroc",
    "auprc",
    "area under the curve",
    "accuracy",
    "precision",
    "recall",
    "f1",
    "f1 score",
    "f-score",
    "sensitivity",
    "specificity",
    "pearson",
    "spearman",
    "correlation",
    "r2",
    "r²",  # "r²"
    "r-squared",
    "mse",
    "rmse",
    "mae",
    "dice",
    "iou",
    "fold change",
    "log2 fold change",
    "log fold change",
)

# How far (chars) past a metric word the number may sit. Kept tight so prose
# noise is not swept in; widen only if a fixture shows a real miss.
_MAX_GAP = 40

# A number: signed decimal, optional scientific notation, optional trailing `%`.
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?%?")

# A connective that joins a metric to its number. Word connectives use ASCII
# word boundaries; `=`/`:` are symbol connectives.
_CONNECTIVE = re.compile(
    r"(?:\bof\b|\bwas\b|\bis\b|\breached\b|\bachieved\b|\bat\b|=|:)",
    re.IGNORECASE,
)

# The vocabulary as one alternation, longest phrase first so it wins at a given
# position. ASCII-alnum lookarounds (not `\b`) so odd metrics like "r²" -- whose
# trailing char is not an ASCII/`\w` word char -- still delimit cleanly.
_METRIC = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(re.escape(m) for m in sorted(_METRIC_VOCAB, key=len, reverse=True))
    + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Inequality operators: a number immediately preceded by one of these (after a
# connective/whitespace trim) is a bound, not a point value, so it is skipped.
_INEQUALITIES = ("<=", ">=", "<", ">", "≤", "≥")  # includes ≤, ≥


def _slug(metric: str) -> str:
    """Deterministic, human-editable id slug of a metric word.

    Lowercase, every run of non-ASCII-alphanumeric characters collapsed to a
    single `_`, then stripped of leading/trailing `_`. So "log2 fold change" ->
    "log2_fold_change", "r-squared" -> "r_squared", "F1 score" -> "f1_score".
    The superscript form "R²" (R²) collapses its non-ASCII `²` to `_`
    and strips it, yielding "r" (pinned rule). An all-non-alnum metric would
    slug to "" -- degraded to "claim" so an id is always non-empty. Pure.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", metric.lower()).strip("_")
    return slug or "claim"


def _parse_number(token: str) -> tuple[float | None, str | None]:
    """Parse a matched number token into `(value, unit)`.

    A trailing `%` sets `unit="%"` and is stripped before parsing -- the value
    is the RAW number (`87` from "87%"), never divided by 100. Any parse
    failure or a non-finite result (e.g. an overflowing exponent) degrades to
    `(None, None)`. Pure, never raises.
    """
    unit: str | None = None
    body = token
    if body.endswith("%"):
        unit = "%"
        body = body[:-1]
    try:
        value = float(body)
    except (ValueError, TypeError):
        return None, None
    if not math.isfinite(value):
        return None, None
    return value, unit


def _sentence_around(text: str, start: int, end: int) -> str:
    """Return the sentence spanning `[start, end)` in `text` (provenance).

    Boundaries are a newline, or one of `. ! ?` followed by whitespace/end (so a
    decimal point inside a number never splits it). Index-safe, never raises.
    """
    n = len(text)

    def _is_boundary(i: int) -> bool:
        ch = text[i]
        if ch == "\n":
            return True
        if ch in ".!?":
            return i + 1 >= n or text[i + 1].isspace()
        return False

    left = start
    while left > 0:
        if _is_boundary(left - 1):
            break
        left -= 1

    right = end
    while right < n:
        if _is_boundary(right):
            # Include a sentence-final punctuation mark; a newline is dropped.
            right += 0 if text[right] == "\n" else 1
            break
        right += 1

    return text[left:right].strip()


def extract_claims(text: str) -> list[ExtractedClaim]:
    """Extract candidate named-metric numeric claims from `text`.

    Deterministic and precision-favoring. For each vocabulary metric found, the
    first number within `_MAX_GAP` chars is bound to it only when a connective
    sits between them and no inequality immediately precedes the number; a
    metric whose gap to the number already contains ANOTHER metric is skipped
    (the nearer metric owns the number). Percentages keep the raw value plus a
    `"%"` unit. Claims are de-duped file-wide on `(metric_slug, value)` keeping
    the first occurrence, emitted in first-appearance order, with ids the metric
    slug uniquified (`auc`, `auc_2`, ...).

    Never raises: non-str input, or any per-candidate parse issue, degrades to
    skipping (an empty list in the worst case).
    """
    if not isinstance(text, str) or not text:
        return []

    claims: list[ExtractedClaim] = []
    seen_keys: set[tuple[str, float]] = set()
    used_ids: set[str] = set()

    for match in _METRIC.finditer(text):
        try:
            metric_text = match.group(0)
            gap_start = match.end()
            window = text[gap_start : gap_start + _MAX_GAP]

            num_match = _NUMBER.search(window)
            if num_match is None:
                continue
            gap = window[: num_match.start()]

            # The number must be joined to the metric by a connective, and the
            # gap must not already contain another metric (that later metric is
            # the real owner of this number).
            if _CONNECTIVE.search(gap) is None:
                continue
            if _METRIC.search(gap) is not None:
                continue

            # Inequality: a bound, not a point value -> skip.
            if gap.rstrip().endswith(_INEQUALITIES):
                continue

            value, unit = _parse_number(num_match.group(0))
            if value is None:
                continue

            slug = _slug(metric_text)
            key = (slug, value)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            claim_id = _unique_id(slug, used_ids)
            num_end = gap_start + num_match.end()
            source_text = _sentence_around(text, match.start(), num_end)

            claims.append(
                ExtractedClaim(
                    id=claim_id,
                    value=value,
                    metric=metric_text,
                    unit=unit,
                    source_text=source_text,
                )
            )
        except Exception:
            # Belt-and-suspenders: one pathological candidate can never crash
            # the extraction. The pieces above are already total; this only
            # guarantees the never-raises contract holds unconditionally.
            continue

    return claims


def _unique_id(slug: str, used_ids: set[str]) -> str:
    """Uniquify `slug` against `used_ids`: `slug`, then `slug_2`, `slug_3`, ...

    Deterministic (no randomness -- ids must be reproducible / journal-safe).
    Mutates `used_ids` with the chosen id.
    """
    if slug not in used_ids:
        used_ids.add(slug)
        return slug
    n = 2
    while f"{slug}_{n}" in used_ids:
        n += 1
    candidate = f"{slug}_{n}"
    used_ids.add(candidate)
    return candidate


# --- optional, env-gated LLM assist (aspect `llm-assist`) ----------------------
# A pure no-op unless a provider AND its key are configured (the gate is
# `detect._selected_provider`, the single source of truth shared with the `llm`
# detector). When configured, one prompt is sent through `_llm_complete` -- the
# ONLY place a provider SDK is imported (lazily) or the network is touched -- and
# the reply is parsed defensively. Every failure (provider/network/parse/shape)
# degrades to `[]`: the deterministic core always stands alone.


def _build_extraction_prompt(text: str) -> str:
    """One prompt asking for a strict JSON list of numeric claims.

    The contract (shared with `cli-command` and the review sidecar) is a JSON
    list of `{"metric": str, "value": number, "unit": str|null,
    "source_text": str}` and nothing else.
    """
    return (
        "You are a scientific-paper claim extractor. From the paper text below, "
        "extract every quantitative result claim: a named metric bound to a "
        "numeric value.\n\n"
        'Reply with ONLY a JSON list of objects, each '
        '{"metric": string, "value": number, "unit": string or null, '
        '"source_text": string (the sentence the value came from)}. '
        "For a percentage use the raw number and unit \"%\" (87, not 0.87). "
        "Return [] if there are no claims. Output the JSON list and nothing else."
        "\n\nPaper text:\n" + text + "\n"
    )


def _llm_complete(provider: str, prompt: str) -> str:
    """Send one prompt to the selected provider and return the raw text reply.

    This is the ONLY place a provider SDK is imported (lazily) or the network is
    touched, so the whole assist is mocked by monkeypatching this one function.
    Its shape mirrors `detect._llm_complete` but it is a SEPARATE, module-local
    seam so extraction is mockable independently of the failure detector. The API
    key is read from env here and never logged or returned.
    """
    key_env = detect._LLM_PROVIDER_KEY_ENV[provider]
    api_key = os.environ[key_env]
    if provider == "claude":
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
    # openai
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content or ""


def _claims_from_reply(reply: str) -> list[ExtractedClaim]:
    """Parse a model reply into `ExtractedClaim`s, swallowing every error.

    Tolerant of a JSON list wrapped in prose (list-analogue of
    `detect._extract_json_object`). Each entry needs a finite, non-bool numeric
    `value`; ids are the same slug+uniquify rule as the core; `origin="llm"`.
    Any provider/parse/shape problem (including a raised exception) degrades to
    `[]` -- this never raises (mirrors `_diagnosis_from_reply`).
    """
    try:
        entries = _extract_json_list(reply)
        if entries is None:
            return []
        claims: list[ExtractedClaim] = []
        used_ids: set[str] = set()
        for entry in entries:
            claim = _claim_from_entry(entry, used_ids)
            if claim is not None:
                claims.append(claim)
        return claims
    except Exception:
        return []


def _extract_json_list(text: str) -> list | None:
    """Parse a top-level JSON list out of a reply, or None if not a list."""
    stripped = text.strip()
    try:
        obj = json.loads(stripped)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, list) else None


def _claim_from_entry(entry: object, used_ids: set[str]) -> ExtractedClaim | None:
    """Build one llm-origin `ExtractedClaim` from a reply entry, or None.

    Requires a dict with a finite, non-bool numeric `value`. `metric`, `unit`
    and `source_text` are coerced to their expected types; a missing/invalid
    entry contributes nothing (skipped, never raised).
    """
    if not isinstance(entry, dict):
        return None
    raw_value = entry.get("value")
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        return None
    value = float(raw_value)
    if not math.isfinite(value):
        return None
    metric = str(entry.get("metric") or "")
    raw_unit = entry.get("unit")
    unit = str(raw_unit) if isinstance(raw_unit, str) and raw_unit else None
    source_text = str(entry.get("source_text") or "")
    claim_id = _unique_id(_slug(metric), used_ids)
    return ExtractedClaim(
        id=claim_id,
        value=value,
        metric=metric,
        unit=unit,
        source_text=source_text,
        origin="llm",
    )


def extract_with_llm(text: str) -> list[ExtractedClaim]:
    """Optional LLM assist: extra candidate claims, or `[]` when unconfigured.

    Gated by `detect._selected_provider()` (the shared env gate): unconfigured
    (`CONTIG_LLM_PROVIDER` unset / unknown / missing key) returns `[]` without
    importing a provider SDK or touching the network. When configured, one
    extraction prompt is sent through the module-local `_llm_complete` seam and
    the reply is parsed defensively. Never raises.
    """
    provider = detect._selected_provider()
    if provider is None:
        return []
    try:
        reply = _llm_complete(provider, _build_extraction_prompt(text))
    except Exception:
        # A provider/network error must never crash extraction; degrade to the
        # deterministic core alone. The exception is intentionally not logged
        # (it can carry request context, including the key).
        return []
    return _claims_from_reply(reply)
