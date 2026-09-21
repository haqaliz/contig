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
not a match, whatever the scale; shape-malformed candidates are skipped.
`match_claims` applies the full matching rule (M4 site grouping, M5 dual-scale
exactly-one, M9 refusal, in claims order, never raising) and the sidecar
builder (`sidecar_text`) renders the per-claim provenance (S2) -- the artifact,
coordinate, and scale a bound claim proposes, with the R6 disclosure (the exact
repo-relative path whose rewriting the locator depends on) stated as a fact,
and the reason + candidate count for every non-bound claim, under the R1
"proposed, pending human review" framing that appears exactly once.

M10 (semantic filter): `match_claims` takes an optional
`metrics: Mapping[str, Sequence[str]] | None` (claim id -> metric words, from
the extractor -- never invented here). When the claim has words AND at least
one candidate's table header (str column, header mode) or JSON leaf key
normalized-matches a word, the pool is FILTERED to that semantic subset before
any value matching, and the outcome's `semantic_match` names the matched
key(s). The filter can only narrow a pool; no words, unknown claim id, or zero
header matches fall back to the byte-identical value-only behavior. The
value-only rules (printed precision, exactly-one, dual-scale, site grouping,
M9) run unchanged inside the subset.

Stdlib only; dataclasses imported from the shipped modules and never edited.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from contig.verification.locator_inference import Candidate, SweepSkip
from contig.verification.reproduce import Claim, Locator, TableLocator, _parse_path

#: Sentinel `_printed_precision` returns for a scientific-notation repr
#: (`1e-05`, `1.5e-07`): the claim's printed digits are not a decimal-place
#: count, so comparison is EXACT -- no rounding at any scale. Documented
#: default, pinned by tests; never a real decimal-place count (hence negative).
_EXACT_COMPARE = -1

#: M9's low-information deny-list (frozenset of floats): `0`, `1`, `0.5`,
#: `0.05`, `100` in every float form (`0` and `0.0` are the same float).
#: Small/round values appear all over a real repo, so a claim carrying one is
#: refused outright, never bound. A conservative, deliberately uncalibrated
#: engineering default, named as such in the PRD.
_LOW_INFORMATION_DENY = frozenset({0.0, 1.0, 0.5, 0.05, 100.0})

#: M9's significant-digit cap for integer-valued claims: an integer with at
#: most this many significant digits (trailing zeros ignored: `87` and `870`
#: both count 2) is too low-information to bind. Conservative uncalibrated
#: default; `876` (3) and `1234` (4) pass.
_INT_SIG_DIGIT_CAP = 2


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
    `semantic_match` (M10) is the header/leaf key -- or sorted comma-joined
    keys when several distinct ones matched -- that narrowed the candidate
    pool; `None` when the value-only path ran (no metrics, unknown claim
    id, or zero header matches).
    """

    claim_id: str
    value: float
    scale: Literal["raw", "pct"] | None
    locator: Locator | TableLocator | None
    site_count: int
    reason: Literal["bound", "ambiguous", "refused_low_information", "no_candidates"]
    semantic_match: str | None = None  # M10: header/leaf key(s) that narrowed the pool


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


def _significant_digits(value: float) -> int:
    """Count the significant digits of the integer-valued claim `value`:
    the number of digits in its magnitude with trailing zeros ignored --
    `87` -> 2, `870` -> 2, `876` -> 3, `1234` -> 4, `1000000` -> 1. The
    exact rule: `len(str(abs(int(value))).rstrip("0"))`. Only ever called
    with an integer-valued (and finite) value, so the `int()` conversion
    cannot raise (M7); a value of `0` would count 0, but `0` is denied by
    `_LOW_INFORMATION_DENY` before this ever runs.
    """
    return len(str(abs(int(value))).rstrip("0"))


def _is_low_information(value: float) -> bool:
    """True iff claim `value` is M9-refused: on the deny-list, or an
    integer-valued value with at most `_INT_SIG_DIGIT_CAP` significant
    digits. Non-integer floats like `0.75` are only ever refused by the
    deny-list -- the significant-digit rule never touches them. Never
    raises: non-finite values are caught by the caller before this runs,
    and `float.is_integer()` is False for them regardless (M7).
    """
    if value in _LOW_INFORMATION_DENY:
        return True
    if not value.is_integer():
        return False
    return _significant_digits(value) <= _INT_SIG_DIGIT_CAP


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


def _norm_header(s: str) -> str:
    """Normalize a header or metric word for semantic comparison (M10):
    lowercase and keep alphanumerics only. `"Recovery %"` -> `"recovery"`,
    `"log2FoldChange"` -> `"log2foldchange"`, `"n_recovered"` ->
    `"nrecovered"`. The separators are gone, so the result is one
    contiguous alnum run; equality is judged on this form. Deliberately
    conservative: no token-boundary rule is defined -- containment (below)
    is judged on the UN-normalized lowercased forms precisely so that a
    multi-word metric phrase like `"fold change"` does not silently match
    inside `"log2FoldChange"` (the space is a real character there, and
    `"fold change"` is not a substring). Documented default, pinned.
    """
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _header_matches(header: str, words: Sequence[str]) -> bool:
    """True iff `header` semantic-matches any metric `word` (M10):
    normalized equality, OR containment in either direction -- word in
    header (`"recovered"` in `"n_recovered"`) or header in word
    (`"recovery"` in `"recovery_rate"`). Containment is judged on the
    lowercased UN-normalized forms (separators kept), so `"Recovery %"`
    matches `"recovery"` by equality, while `"log2FoldChange"` does NOT
    match `"fold change"` -- the space in the phrase breaks the substring
    and no token-boundary rule is defined (documented default, pinned).
    Non-str and empty words are skipped, never raised on (M7): garbage
    metric values degrade to no-match, which the caller treats as the
    value-only fallback.
    """
    header_norm = _norm_header(header)
    header_lower = header.lower()
    for word in words:
        if not isinstance(word, str):
            continue
        word_norm = _norm_header(word)
        if not word_norm:
            continue
        if word_norm == header_norm:
            return True
        word_lower = word.lower()
        if word_lower in header_lower or header_lower in word_lower:
            return True
    return False


def _leaf_key(path: str) -> str | None:
    """The semantic name of a JSON leaf candidate: the last STRING token of
    its dotted+`[n]` path, via the shipped `_parse_path` (the same grammar
    the sweep round-trips). `"m.auc"` -> `"auc"`, `"rows[0].v"` -> `"v"`; a
    list-index tail (`"xs[0]"`) ends in an int token, which is no key --
    None, so that candidate has no semantic name and can never enter the
    semantic subset (documented; a future key-inference is out of scope).
    """
    tokens = _parse_path(path)
    if tokens is None:
        return None
    tail = tokens[-1]
    if isinstance(tail, int):
        return None
    return tail


def _candidate_semantic_name(candidate: Candidate) -> str | None:
    """The semantic name a `candidate` can be narrowed by (M10): the table
    `column` when it is a str (header mode -- headerless int columns have
    no semantic name), or the JSON leaf key; None means the candidate has
    no semantic name and can never join a semantic subset.
    """
    if candidate.kind == "json":
        if candidate.path is None:
            return None
        return _leaf_key(candidate.path)
    if candidate.kind == "table":
        if isinstance(candidate.column, str):
            return candidate.column
        return None
    return None


def _site_key(candidate: Candidate) -> tuple:
    """A site is a distinct (source, coordinate) pair (M4): `(source,
    path)` for a JSON leaf, `(source, column, row)` for a table cell. Two
    candidates with the same key (e.g. duplicated table rows) are ONE site,
    never ambiguity. Only called on shape-valid candidates (kind "json"
    with `path` set, or "table" with `column`/`row`/`header` set -- the
    defensive skips in `_match_one_claim` guarantee it).
    """
    if candidate.kind == "json":
        return (candidate.source, candidate.path)
    return (candidate.source, candidate.column, candidate.row)


def _locator_for(candidate: Candidate) -> Locator | TableLocator:
    """Build the proposed binding site for a matched `candidate`, fields
    carried VERBATIM from the `Candidate` -- `source` is the repo-relative
    POSIX path, `path` is the sweep's dotted+`[n]` expression (never
    synthesized), `column`/`row`/`header` come 1:1. `TableLocator.delimiter`
    is never set (the empty-string sentinel): `load_claims` re-derives it
    from the source extension, and setting a delimiter here would be a trap
    that silently drifts from what load time resolves.
    """
    if candidate.kind == "json":
        return Locator(source=candidate.source, path=candidate.path)
    return TableLocator(
        source=candidate.source,
        column=candidate.column,
        row=candidate.row,
        delimiter="",
        header=candidate.header,
    )


def _match_one_claim(
    candidates: Sequence[Candidate],
    claim: Claim,
    metrics: Mapping[str, Sequence[str]] | None = None,
) -> MatchOutcome:
    """Match one claim against the candidate sweep, never raising (M7).

    Order of judgment, per claim: a non-finite value (a `nan`/`inf` claim,
    loadable by `load_claims`) records `no_candidates` -- it can never be
    evidence; M9 refuses a low-information value BEFORE any matching runs
    (the refusal short-circuits, `site_count=0` -- even a candidate that
    would match must not bind); the M10 semantic filter (when `metrics`
    gives this claim words AND at least one candidate's header/leaf key
    normalized-matches a word) narrows the pool to the semantic subset and
    records `semantic_match`; then both scales are attempted independently
    (`"raw"` and `"pct"`), collecting the DISTINCT sites (M4) where any
    candidate in the pool matches at the claim's own printed precision.
    Exactly one scale with exactly one site binds; both scales with one
    site each, or either scale with more than one site, is ambiguous with
    the total distinct-site count; zero sites is `no_candidates`.

    The semantic filter can only narrow a pool, never widen it: no metric
    words (`None`/empty/garbage), an unknown claim id, or zero header
    matches all fall back to the full value-only pool, byte-identical to
    the shipped behavior. `semantic_match` is set whenever the filter ran
    for the claim -- including a semantic `no_candidates` miss -- and is
    `None` only on the value-only path.

    Candidates are iterated in the given order (already sorted by source
    from `sweep_repo` -- never re-sorted), and the first candidate seen at
    a site is the site's representative, so outcomes are reproducible.
    Shape-malformed candidates (unknown `kind`, `kind="json"` without
    `path`, `kind="table"` without `column`/`row`/`header`) are skipped,
    never raised on, never counted as sites.
    """
    value = float(claim.value)
    if not math.isfinite(value):
        return MatchOutcome(claim.id, value, None, None, 0, "no_candidates")
    if _is_low_information(value):
        return MatchOutcome(claim.id, value, None, None, 0, "refused_low_information")

    precision = _printed_precision(value)
    semantic_match = None
    pool = candidates
    if metrics is not None:
        words = metrics.get(claim.id)
        if isinstance(words, str):
            words = (words,)
        if isinstance(words, (list, tuple)) and words:
            semantic_pool: list[Candidate] = []
            matched_keys: set[str] = set()
            for candidate in candidates:
                name = _candidate_semantic_name(candidate)
                if name is not None and _header_matches(name, words):
                    semantic_pool.append(candidate)
                    matched_keys.add(name)
            if semantic_pool:
                pool = semantic_pool
                semantic_match = ", ".join(sorted(matched_keys))

    raw_sites: dict[tuple, Candidate] = {}
    pct_sites: dict[tuple, Candidate] = {}
    for candidate in pool:
        if candidate.kind == "json":
            if candidate.path is None:
                continue
        elif candidate.kind == "table":
            if (
                candidate.column is None
                or candidate.row is None
                or candidate.header is None
            ):
                continue
        else:
            continue
        if _value_matches(candidate.value, value, "raw", precision):
            raw_sites.setdefault(_site_key(candidate), candidate)
        if _value_matches(candidate.value, value, "pct", precision):
            pct_sites.setdefault(_site_key(candidate), candidate)

    if len(raw_sites) == 1 and not pct_sites:
        return MatchOutcome(
            claim.id, value, "raw", _locator_for(next(iter(raw_sites.values()))), 1,
            "bound", semantic_match,
        )
    if len(pct_sites) == 1 and not raw_sites:
        return MatchOutcome(
            claim.id, value, "pct", _locator_for(next(iter(pct_sites.values()))), 1,
            "bound", semantic_match,
        )
    if not raw_sites and not pct_sites:
        return MatchOutcome(
            claim.id, value, None, None, 0, "no_candidates", semantic_match
        )
    total_sites = len(set(raw_sites) | set(pct_sites))
    return MatchOutcome(
        claim.id, value, None, None, total_sites, "ambiguous", semantic_match
    )


def match_claims(
    candidates: Sequence[Candidate],
    claims: Sequence[Claim],
    *,
    metrics: Mapping[str, Sequence[str]] | None = None,
) -> list[MatchOutcome]:
    """Match sweep candidates against claims, one outcome per claim in
    claims order, pure and never raising (M7).

    `metrics` (M10) maps a claim id to its metric words; when the claim has
    words AND at least one candidate's header/leaf key normalized-matches a
    word, the candidate pool is filtered to the semantic subset before any
    value matching, and the outcome's `semantic_match` names the matched
    key(s). No words, an unknown claim id, or zero header matches fall back
    to the value-only behavior, byte-identical to the shipped module. A
    non-dict `metrics` raises `TypeError` at call time (pinned); garbage
    metric values degrade to fallback, never raising.

    A `bound` outcome carries the complete locator and the scale at which
    the repo held the value (`"raw"` = `v`, `"pct"` = `v/100`); every other
    reason carries `locator=None`/`scale=None` and the evidence count in
    `site_count` (distinct (source, coordinate) sites holding a matching
    value, across both scales where the outcome is ambiguous). Empty
    `claims` yields `[]`; empty `candidates` yields one `no_candidates`
    outcome per claim.
    """
    if metrics is not None and not isinstance(metrics, dict):
        raise TypeError("metrics must be a dict or None")
    return [_match_one_claim(candidates, claim, metrics) for claim in claims]


#: The sidecar's once-only R1 framing line (S2): the matcher's proposals are
#: evidence-gated but self-graded, so the rendered text must carry the
#: "proposed, pending human review" framing exactly once, before any per-claim
#: line. Pinned by a substring test.
_SIDECAR_HEADER = (
    "# The locator proposals below are proposed, pending human review; a "
    "fresh run decides every verdict."
)


def _sidecar_coordinate(locator: Locator | TableLocator) -> str:
    """The coordinate of a bound locator as sidecar text: the JSON dotted
    `path`, or the table `column`/`row`/`header` triplet (M3 -- fields come
    1:1 from the locator, `delimiter` never shown because the matcher never
    sets it).
    """
    if isinstance(locator, TableLocator):
        return (
            f"column={locator.column}, row={locator.row}, "
            f"header={locator.header}"
        )
    return f"path={locator.path}"


def _sidecar_line(outcome: MatchOutcome) -> str:
    """One claim's sidecar line (S2). A bound line names the claim id, the
    artifact (repo-relative `source`), the coordinate, the scale (`raw` /
    `÷100`), and the R6 disclosure -- the exact repo-relative path whose
    rewriting the locator depends on (the same `source`, stated as a fact,
    never a guarantee). When the outcome's pool was narrowed by the M10
    semantic filter (`semantic_match` set), the bound line names it too --
    "via column <key>" for a table bind, "via key <key>" for a JSON leaf
    bind -- and the ambiguous / no_candidates lines name the semantic path
    ("semantic subset, N candidate sites" / "semantic column <key>"). A
    value-only outcome renders byte-identical to the shipped wording. Never
    raises: a `bound` outcome without a locator (impossible from
    `match_claims`, defensive against hand-built input) degrades to a named
    line rather than an AttributeError (M7).
    """
    if outcome.reason != "bound":
        if outcome.semantic_match is not None:
            if outcome.reason == "ambiguous":
                return (
                    f"claim {outcome.claim_id}: ambiguous "
                    f"(semantic subset, {outcome.site_count} candidate sites)"
                )
            if outcome.reason == "no_candidates":
                return (
                    f"claim {outcome.claim_id}: no_candidates "
                    f"(semantic column {outcome.semantic_match}, "
                    f"{outcome.site_count} candidate sites)"
                )
        return (
            f"claim {outcome.claim_id}: {outcome.reason} "
            f"({outcome.site_count} candidate sites)"
        )
    locator = outcome.locator
    if locator is None:
        return f"claim {outcome.claim_id}: bound (locator unavailable)"
    scale = "raw" if outcome.scale == "raw" else "÷100"
    semantic = ""
    if outcome.semantic_match is not None:
        kind = "column" if isinstance(locator, TableLocator) else "key"
        semantic = f" via {kind} {outcome.semantic_match}"
    return (
        f"claim {outcome.claim_id}: bound at {locator.source} "
        f"({_sidecar_coordinate(locator)}){semantic} at {scale}; depends on "
        f"{locator.source} being rewritten by the run"
    )


def sidecar_text(
    outcomes: Sequence[MatchOutcome], claims: Sequence[Claim]
) -> str:
    """Render per-claim provenance text (S2), pure and deterministic.

    One line per claim, in claims order (pairs are zipped, so a mismatch
    between the sequences degrades to the shorter length -- never raises,
    M7). The first line is the R1 framing -- "proposed, pending human
    review" -- rendered exactly once, before every per-claim line; empty
    outcomes yield the framing line alone. A bound line names the artifact
    (repo-relative path), the coordinate, the scale (`raw` / `÷100`), and
    the R6 disclosure (the exact path whose rewriting the locator depends
    on, stated as a fact); when `semantic_match` is set it names the M10
    narrowed path too ("via column <key>" / "via key <key>"). A non-bound
    line names the reason and the candidate-site count, naming the semantic
    subset ("semantic subset, N candidate sites") or column ("semantic
    column <key>") for semantic outcomes; value-only lines keep the shipped
    wording. The same inputs always render the identical string: no I/O, no
    wall clock, no iteration order outside the caller's.
    """
    lines = [_SIDECAR_HEADER]
    lines.extend(
        _sidecar_line(outcome) for outcome, _claim in zip(outcomes, claims)
    )
    return "\n".join(lines) + "\n"