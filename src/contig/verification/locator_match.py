"""Evidence-gated matching of sweep candidates against a paper's claimed
values (match-and-propose aspect, Phase 1: the printed-precision equality
core).

The shipped candidate sweep (`locator_inference.sweep_repo`) enumerates every
numeric value in a repo's JSON/table artifacts as a re-resolvable coordinate;
this module matches those `Candidate`s against claims and -- only on
unambiguous evidence -- proposes a binding site. The honest-read contract is
the load-bearing one (G1, self-graded): **nothing here infers from the
paper**. A claim's value is evidence; a candidate is evidence; the only
judgment is whether two printed numbers agree at the claim's own printed
precision. Low-information matches are refused, ambiguous matches are
disclosed, absent candidates are disclosed -- the sidecar (Phase 3) renders
what was and was not proposed, and the R6 disclosure (which repo-relative
path each locator depends on) is stated as a fact, never a guarantee.

`_printed_precision` and `_value_matches` pin the equality semantics BEFORE
any matching logic: a candidate matches when it equals the claim value rounded
to the claim's own repr-derived precision (R3 settlement). An integer-valued
claim compares EXACTLY, never through a rounding window (`875.6` must not
match `876`); a scientific-notation repr (`1e-05`) selects exact comparison
via the `_EXACT_COMPARE` sentinel; and the pct scale applies the same rules to
`claim_value / 100` with two extra decimal places of precision.

**Nothing here raises** (M7): a non-finite candidate or claim value is simply
not a match, whatever the scale. The full matching rule (`match_claims`) and
the sidecar builder (`sidecar_text`) are pinned as callable stubs in Phase 1
and implemented in Phases 2 and 3.

Stdlib only; dataclasses imported from the shipped modules and never edited.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

from contig.verification.locator_inference import Candidate, SweepSkip
from contig.verification.reproduce import Claim, Locator, TableLocator

#: Sentinel `_printed_precision` returns for a scientific-notation repr
#: (`1e-05`, `1.5e-07`): the claim's printed digits are not a decimal-place
#: count, so comparison is EXACT -- no rounding at any scale. Documented
#: default, pinned by tests; never a real decimal-place count (hence negative).
_EXACT_COMPARE = -1


@dataclass(frozen=True)
class MatchOutcome:
    """One claim's matching result: `value` is the claim's value, `scale`
    names the scale at which a bound locator matched (`"raw"` or `"pct"`,
    i.e. the repo held `v` or `v/100`), `locator` is the proposed binding
    site (complete `Locator`/`TableLocator` carried verbatim from the matched
    `Candidate`; `TableLocator.delimiter` is never set -- `load_claims`
    re-derives it), `site_count` is the number of distinct (source,
    coordinate) sites holding a matching value, and `reason` says what
    happened. `scale`/`locator` are `None` unless `reason == "bound"`.
    """

    claim_id: str
    value: float
    scale: Literal["raw", "pct"] | None
    locator: Locator | TableLocator | None
    site_count: int
    reason: Literal["bound", "ambiguous", "refused_low_information", "no_candidates"]


def _printed_precision(value: float) -> int:
    """Return the number of decimal places in `value`'s `repr` (R3).

    The claim's own printed precision is what a match must reproduce, so this
    counts the digits after the decimal point in the shortest repr that
    round-trips: `0.9134` -> 4, `0.91` -> 2, `12.5` -> 1. An int-valued float
    prints `87.0` and carries zero meaningful decimal places -> 0. A
    scientific-notation repr (`1e-05`, `1.5e-07`) has no decimal-place count
    at all -> `_EXACT_COMPARE`, meaning "compare exactly, no rounding". The
    count is clamped at 12 decimal places: a claim printed with more digits
    than that cannot be meaningfully distinguished at finer resolution, and
    `round()` at 12+ places is float noise, not precision.
    """
    text = repr(value)
    if "e" in text or "E" in text:
        return _EXACT_COMPARE
    if "." not in text:
        return 0
    fractional = text.split(".", 1)[1]
    if fractional == "0":
        return 0
    return min(len(fractional), 12)


def _value_matches(
    candidate_value: float,
    claim_value: float,
    scale: Literal["raw", "pct"],
    precision: int,
) -> bool:
    """True iff `candidate_value` reproduces `claim_value` at `scale` and
    `precision`.

    Raw scale: an integer-valued claim (`float(claim_value).is_integer()`)
    compares EXACTLY, never through a rounding window -- `round(875.6, 0)` is
    `876.0`, which would let a half-wrong value pass as a match, so
    `875.6` must NOT match `876`. A float-valued claim compares by exact
    equality AFTER rounding both sides to `precision` decimal places:
    `0.9134` matches a claim printed as `0.91` at 2dp. Pct scale: the same
    rules apply to `claim_value / 100` with `precision + 2` (dividing by 100
    shifts two decimal places: claim `87` compares `0.87` at 2dp; claim
    `0.91` compares `0.0091` at 4dp).

    A `precision` of `_EXACT_COMPARE` (scientific-notation claim repr) means
    exact equality at both scales, no rounding.

    A non-finite candidate (`nan`/`inf`, which the sweep already rejects but
    which may reach the matcher defensively) never matches; a non-finite claim
    value returns False -- this function never raises (M7). The int/float
    nuance is Python's own: `7 == 7.0`, so a JSON int leaf candidate matches a
    float claim `7.0`, and the reverse.
    """
    try:
        candidate = float(candidate_value)
        claim = float(claim_value)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(candidate) or not math.isfinite(claim):
        return False
    if scale == "pct":
        claim = claim / 100.0
        if precision != _EXACT_COMPARE:
            precision = precision + 2
    if precision == _EXACT_COMPARE:
        return candidate == claim
    if claim.is_integer():
        return candidate == claim
    return round(candidate, precision) == round(claim, precision)


def match_claims(
    candidates: Sequence[Candidate], claims: Sequence[Claim]
) -> list[MatchOutcome]:
    """Match sweep candidates against claims (Phase 2 -- stub for now)."""
    return []


def sidecar_text(
    outcomes: Sequence[MatchOutcome], claims: Sequence[Claim]
) -> str:
    """Render per-claim provenance text (Phase 3 -- stub for now)."""
    return ""