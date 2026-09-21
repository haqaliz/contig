"""Tests for the locator matcher (match-and-propose aspect): Phase 1 pins the
printed-precision equality core (`MatchOutcome`'s frozen shape,
`_printed_precision`, `_value_matches`), Phase 2 pins the full matching rule
`match_claims` -- site grouping at (source, coordinate) granularity (M4), the
dual-scale exactly-one rule (M5), the M9 low-information refusal (deny-list +
integer significant-digit rule, short-circuiting before matching), and the
never-raises contract (M7). Phase 3 pins the real consumption path (sweep ->
match over inline `tmp_path` fixture repos), the M6 round-trip and G4
verdict-contract pins over the bound fixture corpus, the structural stale-
artifact honesty guarantee (an inferred locator cannot weaken the freshness
guard), and `sidecar_text`'s per-claim provenance rendering (S2), including
the R6 path disclosure and the once-only R1 review framing.
"""

import json
import os
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Literal, get_type_hints

import pytest

from contig.reproduce_guard import claim_family
from contig.verification.locator_inference import Candidate, sweep_repo
from contig.verification.locator_match import (
    MatchOutcome,
    _EXACT_COMPARE,
    _header_matches,
    _leaf_key,
    _norm_header,
    _printed_precision,
    _significant_digits,
    _value_matches,
    match_claims,
    sidecar_text,
)
from contig.verification.reproduce import (
    Claim,
    Locator,
    TableLocator,
    _read_table,
    _resolve_delimiter,
    classify,
    load_claims,
    resolve_cell,
    resolve_pointer,
    run_reproduction,
)


def test_module_exposes_pinned_public_surface():
    assert callable(match_claims)
    assert callable(sidecar_text)


def test_printed_precision_counts_digits_after_the_decimal_point():
    assert _printed_precision(0.9134) == 4
    assert _printed_precision(0.91) == 2
    assert _printed_precision(12.5) == 1


def test_printed_precision_of_int_valued_float_is_zero():
    assert _printed_precision(87.0) == 0


def test_printed_precision_of_scientific_notation_repr_is_exact_compare_sentinel():
    assert _printed_precision(1e-05) == _EXACT_COMPARE
    assert _printed_precision(1.5e-07) == _EXACT_COMPARE
    assert _EXACT_COMPARE < 0


def test_printed_precision_clamps_at_twelve_decimal_places():
    assert _printed_precision(0.123456789012345) == 12


def test_value_matches_float_claim_rounds_candidate_to_claim_precision():
    assert _value_matches(0.9134, 0.91, "raw", 2) is True
    assert _value_matches(0.9154, 0.91, "raw", 2) is False


def test_value_matches_int_valued_claim_requires_exact_equality():
    assert _value_matches(875.6, 876, "raw", 0) is False
    assert _value_matches(876.0, 876, "raw", 0) is True


def test_value_matches_int_candidate_matches_float_claim():
    assert _value_matches(7, 7.0, "raw", 0) is True
    assert _value_matches(7.0, 7, "raw", 0) is True


def test_value_matches_exact_compare_precision_requires_exact_equality():
    assert _value_matches(1e-05, 1e-05, "raw", _EXACT_COMPARE) is True
    assert _value_matches(1.2e-05, 1e-05, "raw", _EXACT_COMPARE) is False


def test_value_matches_pct_scale_divides_claim_value_by_100():
    assert _value_matches(0.87, 87, "pct", 0) is True
    assert _value_matches(0.0091, 0.91, "pct", 2) is True


def test_value_matches_pct_scale_rounding_misses_distant_candidate():
    assert _value_matches(0.8754, 87, "pct", 0) is False


def test_value_matches_pct_scale_int_valued_divided_claim_requires_exact_equality():
    assert _value_matches(876.0, 87600, "pct", 0) is True
    assert _value_matches(875.6, 87600, "pct", 0) is False


def test_value_matches_pct_scale_scientific_notation_compares_exactly():
    assert _value_matches(1e-06, 1e-04, "pct", _EXACT_COMPARE) is True
    assert _value_matches(1.5e-06, 1e-04, "pct", _EXACT_COMPARE) is False


def test_value_matches_non_finite_candidate_never_matches():
    assert _value_matches(float("nan"), 0.91, "raw", 2) is False
    assert _value_matches(float("inf"), 0.91, "raw", 2) is False
    assert _value_matches(float("-inf"), 0.91, "raw", 2) is False


def test_value_matches_non_finite_claim_never_matches_and_never_raises():
    assert _value_matches(0.91, float("nan"), "raw", 2) is False
    assert _value_matches(0.91, float("inf"), "raw", 2) is False


def test_norm_header_lowercases_and_keeps_alphanumerics_only():
    assert _norm_header("Recovery %") == "recovery"
    assert _norm_header("log2FoldChange") == "log2foldchange"
    assert _norm_header("n_recovered") == "nrecovered"
    assert _norm_header("recovery_rate") == "recoveryrate"


def test_header_matches_normalized_equality():
    assert _header_matches("Recovery %", ["recovery"]) is True


def test_header_matches_does_not_match_fold_change_against_log2foldchange():
    assert _header_matches("log2FoldChange", ["fold change"]) is False


def test_header_matches_word_contained_in_header():
    assert _header_matches("n_recovered", ["recovered"]) is True


def test_header_matches_header_contained_in_word():
    assert _header_matches("recovery_rate", ["recovery"]) is True


def test_leaf_key_is_last_string_token_of_path():
    assert _leaf_key("m.auc") == "auc"
    assert _leaf_key("rows[0].v") == "v"


def test_leaf_key_int_tail_has_no_key():
    assert _leaf_key("xs[0]") is None


def test_match_outcome_is_frozen_with_pinned_fields():
    hints = get_type_hints(MatchOutcome)
    assert hints["claim_id"] is str
    assert hints["value"] is float
    assert hints["scale"] == Literal["raw", "pct"] | None
    assert hints["locator"] == Locator | TableLocator | None
    assert hints["site_count"] is int
    assert hints["reason"] == Literal[
        "bound", "ambiguous", "refused_low_information", "no_candidates"
    ]
    assert hints["semantic_match"] == str | None

    outcome = MatchOutcome(
        claim_id="auc",
        value=0.91,
        scale="raw",
        locator=Locator(source="results.json", path="auc"),
        site_count=1,
        reason="bound",
    )
    assert [f.name for f in fields(MatchOutcome)] == [
        "claim_id",
        "value",
        "scale",
        "locator",
        "site_count",
        "reason",
        "semantic_match",
    ]
    assert outcome.semantic_match is None  # additive field, defaults None
    assert (outcome.claim_id, outcome.value, outcome.scale, outcome.site_count) == (
        "auc",
        0.91,
        "raw",
        1,
    )
    assert outcome.locator == Locator(source="results.json", path="auc")
    with pytest.raises(FrozenInstanceError):
        outcome.site_count = 2


def test_single_json_candidate_match_binds_locator_fields_verbatim():
    candidate = Candidate(source="results.json", kind="json", value=0.9134, path="auc")
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "bound"
    assert outcome.scale == "raw"
    assert outcome.site_count == 1
    assert outcome.claim_id == "auc"
    assert outcome.value == 0.91
    assert outcome.locator == Locator(source="results.json", path="auc")
    assert outcome.locator.source == candidate.source
    assert outcome.locator.path == candidate.path


def test_single_table_candidate_header_mode_binds_complete_table_locator_without_delimiter():
    candidate = Candidate(
        source="out/de.tsv",
        kind="table",
        value=1.2,
        column="log2FoldChange",
        row=0,
        header=True,
    )
    claim = Claim(id="lfc", value=1.2, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "bound"
    assert outcome.scale == "raw"
    assert outcome.site_count == 1
    assert outcome.locator == TableLocator(
        source="out/de.tsv",
        column="log2FoldChange",
        row=0,
        delimiter="",
        header=True,
    )
    assert outcome.locator.delimiter == ""


def test_headerless_table_candidate_match_binds():
    candidate = Candidate(
        source="out/counts.tsv",
        kind="table",
        value=876.0,
        column=2,
        row=41,
        header=False,
    )
    claim = Claim(id="count", value=876.0, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "bound"
    assert outcome.scale == "raw"
    assert outcome.site_count == 1
    assert outcome.locator == TableLocator(
        source="out/counts.tsv", column=2, row=41, delimiter="", header=False
    )


def test_same_value_at_two_json_leaves_is_ambiguous():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc"),
        Candidate(source="results.json", kind="json", value=0.9134, path="f1"),
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "ambiguous"
    assert outcome.site_count == 2
    assert outcome.locator is None
    assert outcome.scale is None


def test_same_value_in_one_json_leaf_and_one_table_cell_is_ambiguous():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc"),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.9134,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "ambiguous"
    assert outcome.site_count == 2
    assert outcome.locator is None
    assert outcome.scale is None


def test_same_value_in_two_table_cells_different_rows_is_ambiguous():
    candidates = [
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=1,
            header=True,
        ),
    ]
    claim = Claim(id="lfc", value=0.75, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "ambiguous"
    assert outcome.site_count == 2
    assert outcome.locator is None
    assert outcome.scale is None


def test_duplicate_table_rows_count_as_one_site_and_bind():
    candidates = [
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
    ]
    claim = Claim(id="lfc", value=0.75, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "bound"
    assert outcome.site_count == 1
    assert outcome.scale == "raw"
    assert outcome.locator == TableLocator(
        source="out/de.tsv",
        column="log2FoldChange",
        row=0,
        delimiter="",
        header=True,
    )


def test_pct_scale_int_claim_binds_repo_value_divided_by_100():
    candidate = Candidate(
        source="out/de.tsv",
        kind="table",
        value=8.76,
        column="log2FoldChange",
        row=0,
        header=True,
    )
    claim = Claim(id="lfc", value=876.0, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "bound"
    assert outcome.scale == "pct"
    assert outcome.site_count == 1
    assert outcome.locator == TableLocator(
        source="out/de.tsv",
        column="log2FoldChange",
        row=0,
        delimiter="",
        header=True,
    )


def test_pct_scale_float_claim_binds_repo_value_divided_by_100():
    candidate = Candidate(
        source="out/de.tsv",
        kind="table",
        value=0.0091,
        column="log2FoldChange",
        row=0,
        header=True,
    )
    claim = Claim(id="lfc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "bound"
    assert outcome.scale == "pct"
    assert outcome.site_count == 1


def test_raw_and_pct_both_match_at_different_sites_is_ambiguous():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.91, path="auc"),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.0091,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "ambiguous"
    assert outcome.site_count == 2
    assert outcome.locator is None
    assert outcome.scale is None


@pytest.mark.parametrize(
    "low", [0, 1, 0.5, 0.05, 100, 0.0, 1.0, 0.5, 0.05, 100.0]
)
def test_m9_deny_list_values_are_refused_even_with_a_matching_candidate(low):
    candidate = Candidate(source="results.json", kind="json", value=low, path="auc")
    claim = Claim(id="c", value=low, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "refused_low_information"
    assert outcome.site_count == 0
    assert outcome.locator is None
    assert outcome.scale is None


def test_significant_digits_count_ignores_trailing_zeros():
    assert _significant_digits(87.0) == 2
    assert _significant_digits(870.0) == 2
    assert _significant_digits(876.0) == 3
    assert _significant_digits(1234.0) == 4
    assert _significant_digits(1000000.0) == 1


def test_m9_integer_significant_digit_rule_refuses_or_binds():
    candidates = [
        Candidate(source="r.json", kind="json", value=99.0, path="x"),
        Candidate(source="r.json", kind="json", value=870.0, path="y"),
        Candidate(source="r.json", kind="json", value=1234.0, path="z"),
        Candidate(source="r.json", kind="json", value=1000000.0, path="w"),
    ]
    claims = [
        Claim(id="c87", value=87.0, tolerance=0.05),
        Claim(id="c870", value=870.0, tolerance=0.05),
        Claim(id="c1234", value=1234.0, tolerance=0.05),
        Claim(id="c1m", value=1000000.0, tolerance=0.05),
    ]
    outcomes = match_claims(candidates, claims)
    assert outcomes[0].reason == "refused_low_information"
    assert outcomes[0].site_count == 0
    assert outcomes[1].reason == "refused_low_information"
    assert outcomes[2].reason == "bound"
    assert outcomes[2].locator.path == "z"
    assert outcomes[3].reason == "refused_low_information"


def test_m9_refusal_short_circuits_before_pct_matching():
    candidate = Candidate(
        source="out/de.tsv",
        kind="table",
        value=0.87,
        column="log2FoldChange",
        row=0,
        header=True,
    )
    claim = Claim(id="lfc", value=87.0, tolerance=0.05)
    (outcome,) = match_claims([candidate], [claim])
    assert outcome.reason == "refused_low_information"
    assert outcome.site_count == 0
    assert outcome.locator is None
    assert outcome.scale is None


def test_no_matches_is_no_candidates():
    candidates = [
        Candidate(source="a.json", kind="json", value=1.5, path="x"),
        Candidate(source="b.tsv", kind="table", value=0.75, column="c", row=0, header=True),
    ]
    claim = Claim(id="auc", value=0.9134, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "no_candidates"
    assert outcome.site_count == 0
    assert outcome.locator is None
    assert outcome.scale is None


def test_non_finite_claim_value_is_no_candidates_never_raises():
    claims = [
        Claim(id="inf", value=float("inf"), tolerance=0.05),
        Claim(id="ninf", value=float("-inf"), tolerance=0.05),
        Claim(id="nan", value=float("nan"), tolerance=0.05),
    ]
    outcomes = match_claims([Candidate(source="a.json", kind="json", value=1.5, path="x")], claims)
    assert [o.reason for o in outcomes] == ["no_candidates", "no_candidates", "no_candidates"]
    assert [o.site_count for o in outcomes] == [0, 0, 0]


def test_empty_claims_returns_empty_list():
    candidate = Candidate(source="results.json", kind="json", value=0.9134, path="auc")
    assert match_claims([candidate], []) == []


def test_empty_candidates_yields_no_candidates_per_claim_in_order():
    claims = [
        Claim(id="a", value=0.9134, tolerance=0.05),
        Claim(id="b", value=0.75, tolerance=0.05),
    ]
    outcomes = match_claims([], claims)
    assert [o.claim_id for o in outcomes] == ["a", "b"]
    assert [o.reason for o in outcomes] == ["no_candidates", "no_candidates"]
    assert all(o.site_count == 0 and o.locator is None and o.scale is None for o in outcomes)


def test_malformed_candidates_are_skipped_without_raising():
    candidates = [
        Candidate(source="weird.json", kind="hologram", value=0.9134),
        Candidate(source="broken.json", kind="json", value=0.9134, path=None),
        Candidate(source="t1.tsv", kind="table", value=0.9134, column=None, row=0, header=True),
        Candidate(source="t2.tsv", kind="table", value=0.9134, column="x", row=None, header=True),
        Candidate(source="t3.tsv", kind="table", value=0.9134, column="x", row=0, header=None),
        Candidate(source="results.json", kind="json", value=0.91, path="auc"),
    ]
    claims = [
        Claim(id="a", value=0.91, tolerance=0.05),
        Claim(id="b", value=0.9134, tolerance=0.05),
    ]
    outcomes = match_claims(candidates, claims)
    assert outcomes[0].reason == "bound"
    assert outcomes[0].locator == Locator(source="results.json", path="auc")
    assert outcomes[1].reason == "no_candidates"


def test_claims_order_preserved_across_mixed_outcomes():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc"),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=0,
            header=True,
        ),
        Candidate(
            source="out/de.tsv",
            kind="table",
            value=0.75,
            column="log2FoldChange",
            row=1,
            header=True,
        ),
    ]
    claims = [
        Claim(id="bound_c", value=0.91, tolerance=0.05),
        Claim(id="amb_c", value=0.75, tolerance=0.05),
        Claim(id="ref_c", value=0.5, tolerance=0.05),
        Claim(id="none_c", value=0.42, tolerance=0.05),
    ]
    outcomes = match_claims(candidates, claims)
    assert [o.claim_id for o in outcomes] == ["bound_c", "amb_c", "ref_c", "none_c"]
    assert [o.reason for o in outcomes] == [
        "bound",
        "ambiguous",
        "refused_low_information",
        "no_candidates",
    ]


# --- Phase 3: sweep -> match integration (real sweep_repo over inline repos) --

# A fixed synthetic run-start so freshness is decided purely by the mtimes we
# set with os.utime, never by wall-clock time (test_reproduce.py idiom).
_RUN_START = 1_000_000.0


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _write_table(tmp_path: Path, name: str, rows: list[list[str]]) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join("\t".join(row) for row in rows) + "\n", encoding="utf-8")
    return p


def test_sweep_to_match_json_repo_binds_claim_to_json_leaf(tmp_path):
    _write(tmp_path, "results.json", '{"auc": 0.9134}')

    candidates, skips = sweep_repo(tmp_path)
    assert skips == []
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])

    assert outcome.reason == "bound"
    assert outcome.scale == "raw"
    assert outcome.site_count == 1
    assert outcome.locator == Locator(source="results.json", path="auc")


def test_sweep_to_match_deseq_table_repo_binds_complete_header_mode_table_locator(
    tmp_path,
):
    _write_table(
        tmp_path,
        "de.tsv",
        [
            ["gene_id", "log2FoldChange", "padj"],
            ["ENSG1", "2.1", "0.001"],
        ],
    )

    candidates, skips = sweep_repo(tmp_path)
    assert skips == []
    claim = Claim(id="lfc", value=2.1, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])

    assert outcome.reason == "bound"
    assert outcome.scale == "raw"
    assert outcome.site_count == 1
    assert outcome.locator == TableLocator(
        source="de.tsv",
        column="log2FoldChange",
        row=0,
        delimiter="",
        header=True,
    )


# --- M6 round-trip + G4 verdict-contract pins over the bound fixture corpus --


def _bound_corpus(tmp_path: Path) -> tuple[list[tuple[MatchOutcome, Claim]], Path]:
    """The integration fixture corpus: one repo holding both fixtures (a JSON
    metrics leaf and a DESeq-like TSV), swept and matched against both claims.
    Returns the `(outcome, claim)` pairs plus the repo dir, for the universal
    M6/G4 pins.
    """
    _write(tmp_path, "results.json", '{"auc": 0.9134}')
    _write_table(
        tmp_path,
        "de.tsv",
        [
            ["gene_id", "log2FoldChange", "padj"],
            ["ENSG1", "2.1", "0.001"],
        ],
    )
    candidates, skips = sweep_repo(tmp_path)
    assert skips == []
    claims = [
        Claim(id="auc", value=0.91, tolerance=0.05),
        Claim(id="lfc", value=2.1, tolerance=0.05),
    ]
    outcomes = match_claims(candidates, claims)
    assert [o.reason for o in outcomes] == ["bound", "bound"]
    return list(zip(outcomes, claims)), tmp_path


def _claim_dict_for(outcome: MatchOutcome, tolerance: float = 0.1) -> dict:
    """Assemble the claim dict a human would write from a bound outcome:
    `from` + `path`, or `from` + `column`+`row`+`header`. `delimiter` is
    deliberately absent -- the matcher never sets it (M3) and `load_claims`
    re-derives it at load time.
    """
    assert outcome.reason == "bound"
    assert tolerance > 0
    locator = outcome.locator
    d = {
        "id": outcome.claim_id,
        "value": outcome.value,
        "tolerance": tolerance,
        "from": locator.source,
    }
    if isinstance(locator, TableLocator):
        d["column"] = locator.column
        d["row"] = locator.row
        d["header"] = locator.header
    else:
        d["path"] = locator.path
    return d


def test_m6_round_trip_every_bound_outcome_passes_unchanged_load_claims(tmp_path):
    corpus, repo = _bound_corpus(tmp_path)
    for outcome, claim in corpus:
        claims_path = tmp_path / f"roundtrip_{outcome.claim_id}.json"
        claims_path.write_text(json.dumps([_claim_dict_for(outcome, tolerance=0.1)]))
        loaded = load_claims(claims_path)  # any ClaimsError fails this test
        assert len(loaded) == 1
        assert loaded[0].id == outcome.claim_id
        assert loaded[0].value == outcome.value
        assert loaded[0].tolerance == 0.1
        locator = loaded[0].locator
        if isinstance(outcome.locator, TableLocator):
            assert locator.source == outcome.locator.source
            assert locator.column == outcome.locator.column
            assert locator.row == outcome.locator.row
            assert locator.header == outcome.locator.header
            assert locator.delimiter == "\t"  # re-derived, never the empty sentinel
        else:
            assert locator == outcome.locator


def _re_resolve(locator: Locator | TableLocator, repo: Path) -> float:
    """Re-resolve a bound locator against the fixture artifact through the
    SHIPPED resolvers (`resolve_pointer`/`resolve_cell`) -- the same
    consumption path a reproduce run uses.
    """
    if isinstance(locator, TableLocator):
        path = repo / locator.source
        delimiter = _resolve_delimiter(path.name, None)
        assert delimiter is not None
        rows = _read_table(path, delimiter)
        cell, reason = resolve_cell(rows, locator.column, locator.row, locator.header)
        assert reason == ""
        return float(cell)
    doc = json.loads((repo / locator.source).read_text(encoding="utf-8"))
    target = resolve_pointer(doc, locator.path)
    assert isinstance(target, (int, float)) and not isinstance(target, bool)
    return float(target)


def test_g4_classify_parity_bound_outcomes_reproduce_at_the_claim_precision(
    tmp_path,
):
    corpus, repo = _bound_corpus(tmp_path)
    for outcome, claim in corpus:
        observed = _re_resolve(outcome.locator, repo)
        if outcome.scale == "pct":
            observed = observed * 100  # back to the claim's own scale
        observed = round(observed, _printed_precision(claim.value))
        status, delta, message = classify(
            claimed=claim.value, observed=observed, tolerance=0.1
        )
        assert status == "reproduced"


def test_g4_claim_family_dispatches_inferred_locators_without_raising(tmp_path):
    corpus, repo = _bound_corpus(tmp_path)
    families = {}
    for outcome, claim in corpus:
        claims_path = tmp_path / f"family_{outcome.claim_id}.json"
        claims_path.write_text(json.dumps([_claim_dict_for(outcome, tolerance=0.1)]))
        (loaded,) = load_claims(claims_path)
        families[outcome.claim_id] = claim_family(loaded)
    assert families == {"auc": "json", "lfc": "table"}


# --- stale-artifact honesty: inference cannot weaken the freshness guard -----


def test_inferred_json_locator_over_stale_artifact_is_unverified_never_reproduced(
    tmp_path,
):
    p = _write(tmp_path, "out/metrics.json", '{"auc": 0.9134}')
    os.utime(p, (_RUN_START - 10, _RUN_START - 10))
    candidates, skips = sweep_repo(tmp_path)
    assert skips == []
    claim = Claim(id="auc", value=0.91, tolerance=0.1)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "bound"
    located = Claim(
        id=claim.id, value=claim.value, tolerance=claim.tolerance, locator=outcome.locator
    )

    def noop_executor(argv: list[str], cwd: Path) -> tuple[int, str]:
        return 0, ""

    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=[located],
        executor=noop_executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "rewritten" in result.message
    assert "run start" in result.message


# --- sidecar_text (S2): per-claim provenance, R6 disclosure, R1 framing -------


def _sidecar_outcomes_and_claims() -> tuple[list[MatchOutcome], list[Claim]]:
    outcomes = [
        MatchOutcome(
            claim_id="auc",
            value=0.91,
            scale="raw",
            locator=Locator(source="results.json", path="auc"),
            site_count=1,
            reason="bound",
        ),
        MatchOutcome(
            claim_id="lfc",
            value=2.1,
            scale="pct",
            locator=TableLocator(
                source="de.tsv",
                column="log2FoldChange",
                row=0,
                delimiter="",
                header=True,
            ),
            site_count=1,
            reason="bound",
        ),
        MatchOutcome(
            claim_id="amb", value=0.75, scale=None, locator=None, site_count=2,
            reason="ambiguous",
        ),
        MatchOutcome(
            claim_id="ref", value=0.5, scale=None, locator=None, site_count=0,
            reason="refused_low_information",
        ),
        MatchOutcome(
            claim_id="none", value=0.42, scale=None, locator=None, site_count=0,
            reason="no_candidates",
        ),
    ]
    claims = [Claim(id=o.claim_id, value=o.value, tolerance=0.05) for o in outcomes]
    return outcomes, claims


def test_sidecar_bound_json_line_names_artifact_coordinate_scale_and_r6_disclosure():
    outcomes, claims = _sidecar_outcomes_and_claims()
    text = sidecar_text(outcomes, claims)
    line = next(l for l in text.splitlines() if l.startswith("claim auc:"))
    assert "results.json" in line
    assert "path=auc" in line
    assert "raw" in line
    assert "depends on results.json being rewritten by the run" in line


def test_sidecar_bound_table_pct_line_names_coordinate_and_divide_by_100_scale():
    outcomes, claims = _sidecar_outcomes_and_claims()
    text = sidecar_text(outcomes, claims)
    line = next(l for l in text.splitlines() if l.startswith("claim lfc:"))
    assert "de.tsv" in line
    assert "column=log2FoldChange" in line
    assert "row=0" in line
    assert "header=True" in line
    assert "÷100" in line
    assert "depends on de.tsv being rewritten by the run" in line


def test_sidecar_ambiguous_line_names_reason_and_site_count():
    outcomes, claims = _sidecar_outcomes_and_claims()
    text = sidecar_text(outcomes, claims)
    line = next(l for l in text.splitlines() if l.startswith("claim amb:"))
    assert "ambiguous" in line
    assert "2" in line


def test_sidecar_refused_line_names_reason_and_zero_count():
    outcomes, claims = _sidecar_outcomes_and_claims()
    text = sidecar_text(outcomes, claims)
    line = next(l for l in text.splitlines() if l.startswith("claim ref:"))
    assert "refused_low_information" in line
    assert "0 candidate sites" in line


def test_sidecar_no_candidates_line_names_reason_and_zero_count():
    outcomes, claims = _sidecar_outcomes_and_claims()
    text = sidecar_text(outcomes, claims)
    line = next(l for l in text.splitlines() if l.startswith("claim none:"))
    assert "no_candidates" in line
    assert "0 candidate sites" in line


def test_sidecar_review_framing_appears_exactly_once():
    outcomes, claims = _sidecar_outcomes_and_claims()
    text = sidecar_text(outcomes, claims)
    assert text.count("proposed, pending human review") == 1


def test_sidecar_empty_outcomes_returns_only_the_framing_line():
    text = sidecar_text([], [])
    assert "proposed, pending human review" in text
    assert "claim " not in text


def test_sidecar_is_deterministic_for_identical_inputs():
    outcomes, claims = _sidecar_outcomes_and_claims()
    assert sidecar_text(outcomes, claims) == sidecar_text(outcomes, claims)


def test_sidecar_renders_lines_in_claims_order():
    outcomes, claims = _sidecar_outcomes_and_claims()
    text = sidecar_text(outcomes, claims)
    positions = [text.index(f"claim {o.claim_id}:") for o in outcomes]
    assert positions == sorted(positions)


def test_sidecar_never_raises_on_length_mismatch():
    outcomes, claims = _sidecar_outcomes_and_claims()
    text = sidecar_text(outcomes[:2], claims)
    assert "proposed, pending human review" in text


def test_sidecar_never_raises_on_bound_outcome_with_missing_locator():
    outcome = MatchOutcome(
        claim_id="x", value=0.91, scale="raw", locator=None, site_count=1,
        reason="bound",
    )
    text = sidecar_text([outcome], [Claim(id="x", value=0.91, tolerance=0.05)])
    assert "claim x:" in text


# --- M10 semantic filter (metric words vs headers / JSON leaf keys) -----------


def _dense_recovery_fixture() -> list[Candidate]:
    """The gate-finding fixture: one value at the same scale in four
    columns, so the value-only matcher can never name a site.
    """
    return [
        Candidate(
            source="de.tsv", kind="table", value=0.91,
            column="recovery", row=0, header=True,
        ),
        Candidate(
            source="de.tsv", kind="table", value=0.91,
            column="precision", row=0, header=True,
        ),
        Candidate(
            source="de.tsv", kind="table", value=0.91,
            column="recall", row=0, header=True,
        ),
        Candidate(
            source="de.tsv", kind="table", value=0.91,
            column="f1", row=0, header=True,
        ),
    ]


def test_semantic_bind_narrows_dense_fixture_that_value_only_cannot_bind():
    candidates = _dense_recovery_fixture()
    claim = Claim(id="r", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(
        candidates, [claim], metrics={"r": ["recovery"]}
    )
    assert outcome.reason == "bound"
    assert outcome.scale == "raw"
    assert outcome.site_count == 1
    assert outcome.semantic_match == "recovery"
    assert outcome.locator == TableLocator(
        source="de.tsv", column="recovery", row=0, delimiter="", header=True
    )


def test_semantic_value_only_path_on_same_dense_fixture_is_ambiguous():
    candidates = _dense_recovery_fixture()
    claim = Claim(id="r", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(candidates, [claim])
    assert outcome.reason == "ambiguous"
    assert outcome.site_count == 4
    assert outcome.locator is None
    assert outcome.semantic_match is None


def test_semantic_several_matching_headers_join_sorted_distinct_keys():
    candidates = [
        Candidate(
            source="de.tsv", kind="table", value=0.91,
            column="recovery", row=0, header=True,
        ),
        Candidate(
            source="de.tsv", kind="table", value=0.91,
            column="recovery_rate", row=0, header=True,
        ),
    ]
    claim = Claim(id="r", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(
        candidates, [claim], metrics={"r": ["recovery"]}
    )
    assert outcome.reason == "ambiguous"
    assert outcome.site_count == 2
    assert outcome.semantic_match == "recovery, recovery_rate"


def test_semantic_no_candidates_miss_sets_semantic_match():
    candidates = [
        Candidate(
            source="de.tsv", kind="table", value=0.91,
            column="recovery", row=0, header=True,
        ),
        Candidate(
            source="de.tsv", kind="table", value=0.42,
            column="precision", row=0, header=True,
        ),
    ]
    claim = Claim(id="r", value=0.75, tolerance=0.05)
    (outcome,) = match_claims(
        candidates, [claim], metrics={"r": ["recovery"]}
    )
    assert outcome.reason == "no_candidates"
    assert outcome.site_count == 0
    assert outcome.semantic_match == "recovery"


def test_semantic_unknown_claim_id_falls_back_byte_identical():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc")
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    value_only = match_claims(candidates, [claim])
    semantic = match_claims(
        candidates, [claim], metrics={"other_id": ["auc"]}
    )
    assert semantic == value_only
    assert semantic[0].semantic_match is None


def test_semantic_word_matching_no_header_falls_back_byte_identical():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc")
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    value_only = match_claims(candidates, [claim])
    semantic = match_claims(
        candidates, [claim], metrics={"auc": ["recovery"]}
    )
    assert semantic == value_only
    assert semantic[0].semantic_match is None


def test_semantic_empty_or_foreign_metrics_falls_back_byte_identical():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc")
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    value_only = match_claims(candidates, [claim])
    assert match_claims(candidates, [claim], metrics=None) == value_only
    assert match_claims(candidates, [claim], metrics={}) == value_only
    assert (
        match_claims(candidates, [claim], metrics={"other_id": ["x"]})
        == value_only
    )


def test_semantic_non_dict_metrics_raises_type_error():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc")
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    with pytest.raises(TypeError):
        match_claims(candidates, [claim], metrics="not-a-dict")


def test_semantic_json_leaf_key_matches_word_and_binds():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="m.auc")
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(
        candidates, [claim], metrics={"auc": ["auc"]}
    )
    assert outcome.reason == "bound"
    assert outcome.semantic_match == "auc"
    assert outcome.locator == Locator(source="results.json", path="m.auc")


def test_semantic_list_index_leaf_has_no_key_takes_value_only_path():
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="xs[0]")
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    (outcome,) = match_claims(
        candidates, [claim], metrics={"auc": ["auc"]}
    )
    assert outcome.reason == "bound"
    assert outcome.semantic_match is None
    assert outcome.locator == Locator(source="results.json", path="xs[0]")


@pytest.mark.parametrize(
    "metrics",
    [
        {"auc": None},
        {"auc": []},
        {"auc": [3]},
        {"auc": [None]},
        {"auc": [""]},
    ],
)
def test_semantic_garbage_metrics_values_degrade_to_fallback_never_raise(
    metrics,
):
    candidates = [
        Candidate(source="results.json", kind="json", value=0.9134, path="auc")
    ]
    claim = Claim(id="auc", value=0.91, tolerance=0.05)
    value_only = match_claims(candidates, [claim])
    assert match_claims(candidates, [claim], metrics=metrics) == value_only


def test_semantic_m9_refusal_wins_regardless_of_metrics():
    candidates = [
        Candidate(
            source="de.tsv", kind="table", value=0.5,
            column="recovery", row=0, header=True,
        )
    ]
    claim = Claim(id="r", value=0.5, tolerance=0.05)
    (outcome,) = match_claims(
        candidates, [claim], metrics={"r": ["recovery"]}
    )
    assert outcome.reason == "refused_low_information"
    assert outcome.site_count == 0
    assert outcome.semantic_match is None