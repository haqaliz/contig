"""Boundary tests for C8 slice 1 phase 2: claims loader, tolerance classifier,
and the reproduce run engine.

Strict TDD: this file is written before any of load_claims/classify/run_reproduction
exist in src/contig/verification/reproduce.py.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from contig.verification.reproduce import (
    Claim,
    ClaimsError,
    Locator,
    TableLocator,
    classify,
    load_claims,
    run_reproduction,
)


# ---------------------------------------------------------------------------
# classify()
# ---------------------------------------------------------------------------


def test_classify_exact_match_is_reproduced():
    status, delta, message = classify(claimed=0.9, observed=0.9, tolerance=0.02)
    assert status == "reproduced"
    assert delta == 0.0
    assert message


def test_classify_within_band_but_not_exact_is_within_tolerance():
    status, delta, message = classify(claimed=1.0, observed=1.05, tolerance=0.1)
    assert status == "within_tolerance"
    assert delta == pytest.approx(0.05)
    assert message


def test_classify_outside_band_is_diverged_and_message_names_values():
    status, delta, message = classify(claimed=1.0, observed=1.5, tolerance=0.1)
    assert status == "diverged"
    assert delta == pytest.approx(0.5)
    assert "1.5" in message
    assert "1.0" in message
    assert "0.5" in message


def test_classify_observed_none_is_unverified():
    status, delta, message = classify(claimed=1.0, observed=None, tolerance=0.1)
    assert status == "unverified"
    assert delta is None
    assert message


def test_classify_nan_observed_is_unverified_never_diverged():
    status, delta, message = classify(claimed=1.0, observed=float("nan"), tolerance=0.1)
    assert status == "unverified"
    assert delta is None


def test_classify_inf_observed_is_unverified_never_diverged():
    status, delta, message = classify(claimed=1.0, observed=float("inf"), tolerance=0.1)
    assert status == "unverified"
    assert delta is None


def test_classify_nan_claimed_is_unverified():
    status, delta, message = classify(claimed=float("nan"), observed=1.0, tolerance=0.1)
    assert status == "unverified"
    assert delta is None


def test_classify_zero_claim_and_zero_observed_is_reproduced():
    status, delta, message = classify(claimed=0.0, observed=0.0, tolerance=0.1)
    assert status == "reproduced"
    assert delta == 0.0


def test_classify_zero_claim_and_nonzero_observed_is_diverged_absolute_fallback():
    # Documented case: _relative_delta falls back to abs(observed) when the
    # claimed (reference) value is 0.
    status, delta, message = classify(claimed=0.0, observed=5.0, tolerance=0.1)
    assert status == "diverged"
    assert delta == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# load_claims()
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def test_load_claims_happy_path(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                {"id": "auc", "value": 0.9, "tolerance": 0.05},
                {"id": "accuracy", "value": 0.8},
            ]
        ),
    )
    claims = load_claims(path)
    assert len(claims) == 2
    assert claims[0].id == "auc"
    assert claims[0].value == 0.9
    assert claims[0].tolerance == 0.05
    # default tolerance
    assert claims[1].id == "accuracy"
    assert claims[1].tolerance == 0.1


def test_load_claims_rejects_malformed_json(tmp_path):
    path = _write(tmp_path, "claims.json", "{not valid json")
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_list_top_level(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps({"id": "auc", "value": 0.9}))
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_item_missing_id(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps([{"value": 0.9}]))
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_item_missing_value(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps([{"id": "auc"}]))
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_numeric_value(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps([{"id": "auc", "value": "high"}]))
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_boolean_value(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps([{"id": "auc", "value": True}]))
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_duplicate_id(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9}, {"id": "auc", "value": 0.5}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_positive_tolerance(tmp_path):
    path = _write(
        tmp_path, "claims.json", json.dumps([{"id": "auc", "value": 0.9, "tolerance": 0}])
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_numeric_string_tolerance(tmp_path):
    path = _write(
        tmp_path, "claims.json", json.dumps([{"id": "auc", "value": 0.9, "tolerance": "0.1"}])
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_boolean_tolerance(tmp_path):
    path = _write(
        tmp_path, "claims.json", json.dumps([{"id": "auc", "value": 0.9, "tolerance": True}])
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


# ---------------------------------------------------------------------------
# load_claims() -- output locator ("from" + "path") [C8 slice 1.5, Phase 2]
# ---------------------------------------------------------------------------


def test_load_claims_with_from_and_path_attaches_locator(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": "out/x.json", "path": "$.a"}]),
    )
    claims = load_claims(path)
    assert claims[0].locator == Locator("out/x.json", "$.a")


def test_load_claims_slice1_claim_has_no_locator(tmp_path):
    path = _write(tmp_path, "claims.json", json.dumps([{"id": "auc", "value": 0.9}]))
    claims = load_claims(path)
    assert claims[0].locator is None


def test_load_claims_rejects_from_without_path(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": "out/x.json"}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_path_without_from(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "path": "$.a"}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_string_from(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": 1, "path": "$.a"}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_non_string_path(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": "out/x.json", "path": 1}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_empty_from(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": "  ", "path": "$.a"}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_empty_path(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([{"id": "auc", "value": 0.9, "from": "out/x.json", "path": ""}]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


# ---------------------------------------------------------------------------
# load_claims() -- table locator ("from" + "column"+"row") [C8 slice 3, Phase 1]
# ---------------------------------------------------------------------------


def _claim(**overrides) -> dict:
    base = {"id": "x", "value": 1.0}
    base.update(overrides)
    return base


def test_load_claims_table_locator_named_tsv_defaults_header_and_delimiter(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "results/de.tsv",
                        "column": "log2FoldChange",
                        "row": {"gene_id": "ENSG00000012048"},
                    }
                )
            ]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator == TableLocator(
        "results/de.tsv", "log2FoldChange", {"gene_id": "ENSG00000012048"}, "\t", True
    )


def test_load_claims_table_locator_named_csv_defaults_header_and_delimiter(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "results/de.csv",
                        "column": "log2FoldChange",
                        "row": {"gene_id": "ENSG00000012048"},
                    }
                )
            ]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator == TableLocator(
        "results/de.csv", "log2FoldChange", {"gene_id": "ENSG00000012048"}, ",", True
    )


def test_load_claims_table_locator_positional_headerless(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "out/counts.csv", "column": 2, "row": 41, "header": False})]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator == TableLocator("out/counts.csv", 2, 41, ",", False)


def test_load_claims_table_locator_infers_delimiter_from_tsv_gz(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv.gz", "column": 2, "row": 0, "header": False})]),
    )
    claims = load_claims(path)
    assert claims[0].locator.delimiter == "\t"


def test_load_claims_table_locator_infers_delimiter_from_csv_gz(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.csv.gz", "column": 2, "row": 0, "header": False})]),
    )
    claims = load_claims(path)
    assert claims[0].locator.delimiter == ","


def test_load_claims_table_locator_explicit_delimiter_overrides_extension(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "results/de.tsv",
                        "column": "log2FoldChange",
                        "row": {"gene_id": "X"},
                        "delimiter": ";",
                    }
                )
            ]
        ),
    )
    claims = load_claims(path)
    assert claims[0].locator.delimiter == ";"


def test_load_claims_rejects_path_and_table_fields_together(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "out/x.tsv",
                        "path": "$.a",
                        "column": 0,
                        "row": 0,
                        "header": False,
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_column_without_row(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_without_column(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "row": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_column_float(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": 1.5, "row": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_column_empty_string(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": "", "row": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_column_negative_int(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": -1, "row": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_negative_int(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": -1})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_empty_object(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": {}})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_multi_key_object(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "out/x.tsv",
                        "column": "gene_id",
                        "row": {"a": "1", "b": "2"},
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_object_empty_key(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": {"": "X"}})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_object_non_string_value(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": {"gene_id": 5}})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_delimiter_not_single_char(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "out/x.tsv",
                        "column": "gene_id",
                        "row": 0,
                        "delimiter": ";;",
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_header_not_bool(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": 0, "header": "true"})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_table_fields_without_from(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps([_claim(**{"column": 0, "row": 0})]),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_row_object_with_header_false(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [
                _claim(
                    **{
                        "from": "out/x.tsv",
                        "column": 0,
                        "row": {"gene_id": "X"},
                        "header": False,
                    }
                )
            ]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_column_str_with_header_false(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "out/x.tsv", "column": "gene_id", "row": 0, "header": False})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


def test_load_claims_rejects_unknown_extension_without_delimiter(tmp_path):
    path = _write(
        tmp_path,
        "claims.json",
        json.dumps(
            [_claim(**{"from": "results/out.txt", "column": 0, "row": 0, "header": False})]
        ),
    )
    with pytest.raises(ClaimsError):
        load_claims(path)


# ---------------------------------------------------------------------------
# run_reproduction()
# ---------------------------------------------------------------------------


def _fake_executor(
    exit_code: int, results: dict | None, results_path: str = "results.json", output: str = ""
):
    """Build a fake executor that writes `results` into `repo/results_path`
    (unless `results` is None, in which case no file is written) and returns
    `(exit_code, output)`. Mirrors the injected
    `Callable[[list[str], Path], tuple[int, str]]` seam.
    """

    def executor(argv: list[str], repo: Path) -> tuple[int, str]:
        if results is not None:
            (repo / results_path).write_text(json.dumps(results))
        return exit_code, output

    return executor


def _claims(*specs: tuple[str, float, float]) -> list[Claim]:
    return [Claim(id=cid, value=value, tolerance=tol) for cid, value, tol in specs]


def test_run_reproduction_missing_claim_key_is_unverified(tmp_path):
    claims = _claims(("auc", 0.9, 0.05), ("accuracy", 0.8, 0.05))
    executor = _fake_executor(0, {"auc": 0.9})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
    )
    by_id = {r.id: r for r in record.claim_results}
    assert by_id["auc"].status == "reproduced"
    assert by_id["accuracy"].status == "unverified"
    assert by_id["accuracy"].observed is None


def test_run_reproduction_non_numeric_string_observed_is_unverified(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _fake_executor(0, {"auc": "high"})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
    )
    assert record.claim_results[0].status == "unverified"
    assert record.claim_results[0].observed is None


def test_run_reproduction_boolean_observed_is_unverified(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _fake_executor(0, {"auc": True})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
    )
    assert record.claim_results[0].status == "unverified"
    assert record.claim_results[0].observed is None


def test_run_reproduction_nonzero_exit_marks_all_unverified_and_skips_results(tmp_path):
    claims = _claims(("auc", 0.9, 0.05), ("accuracy", 0.8, 0.05))
    # Even if a results file exists, a nonzero exit must short-circuit before reading it.
    executor = _fake_executor(1, {"auc": 0.9, "accuracy": 0.8})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="false",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
    )
    assert record.exit_code == 1
    assert all(r.status == "unverified" for r in record.claim_results)
    assert all(r.observed is None for r in record.claim_results)
    assert "exit 1" in record.claim_results[0].message


def test_run_reproduction_missing_results_file_marks_all_unverified(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _fake_executor(0, results=None)  # exit 0, but never writes results.json
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
    )
    assert record.claim_results[0].status == "unverified"
    assert record.claim_results[0].observed is None


def test_run_reproduction_unparseable_results_file_marks_all_unverified(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))

    def executor(argv, repo):
        (repo / "results.json").write_text("{not json")
        return 0, ""

    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
    )
    assert record.claim_results[0].status == "unverified"
    assert record.claim_results[0].observed is None


def test_run_reproduction_extra_results_keys_are_ignored(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _fake_executor(0, {"auc": 0.9, "unrelated_metric": 42})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
    )
    assert len(record.claim_results) == 1
    assert record.claim_results[0].status == "reproduced"


def test_run_reproduction_returns_full_record_metadata(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _fake_executor(0, {"auc": 0.9})
    record = run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
    )
    assert record.reproduce_id == "rp_1"
    assert record.repo == str(tmp_path)
    assert record.run_command == "echo run"
    assert record.claims_sha256 == "a" * 64
    assert record.created_at == "2026-07-18T00:00:00Z"
    assert record.exit_code == 0


# ---------------------------------------------------------------------------
# run_reproduction() -- located claims via the output locator [C8 slice 1.5,
# Phase 3]
# ---------------------------------------------------------------------------


def _run(tmp_path: Path, claims: list[Claim], executor, **overrides) -> "object":
    kwargs = dict(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
    )
    kwargs.update(overrides)
    return run_reproduction(**kwargs)


def _write_located(tmp_path: Path, rel: str, payload: object) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload))


def _noop_executor(exit_code: int = 0):
    def executor(argv: list[str], repo: Path) -> tuple[int, str]:
        return exit_code, ""

    return executor


def test_run_reproduction_located_claim_matching_is_reproduced(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "reproduced"
    assert result.observed == 0.9


def test_run_reproduction_located_claim_drifted_is_diverged_with_message(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.5}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "diverged"
    assert result.observed == 0.5
    assert "0.5" in result.message
    assert "0.9" in result.message
    assert result.delta is not None


def test_run_reproduction_located_claim_near_value_is_within_tolerance(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.92}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "within_tolerance"
    assert result.observed == 0.92


def test_run_reproduction_located_claim_missing_file_is_unverified(tmp_path):
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_unparseable_json_is_unverified(tmp_path):
    p = tmp_path / "out" / "summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json")
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_non_utf8_file_is_unverified_not_raise(tmp_path):
    # A non-UTF-8 'from' file makes Path.read_text() raise UnicodeDecodeError,
    # a ValueError subclass -- must be caught alongside JSONDecodeError/OSError
    # and mapped to unverified, never propagate and crash the run.
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "summary.json").write_bytes(b"\xff\xfe\x00bad")
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "not valid JSON" in result.message


def test_run_reproduction_located_claim_unresolved_path_is_unverified(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"acc": 0.9}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_string_target_is_unverified_strict(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": "0.9"}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_numeric_string_target_is_unverified_strict(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": "0.91"}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_boolean_target_is_unverified(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": True}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_nan_target_is_unverified(tmp_path):
    # JSON has no literal NaN/Infinity by spec, but Python's json module accepts
    # them by default (json.dumps(float("nan")) -> "NaN"); write raw text.
    p = tmp_path / "out" / "summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"model": {"auc": NaN}}')
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_located_claim_inf_target_is_unverified(tmp_path):
    p = tmp_path / "out" / "summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"model": {"auc": Infinity}}')
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor())
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None


def test_run_reproduction_mixed_located_and_flat_claims_resolve_independently(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    located = Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))
    flat = Claim(id="accuracy", value=0.8, tolerance=0.05)
    executor = _fake_executor(0, {"accuracy": 0.8})
    record = _run(tmp_path, [located, flat], executor)
    by_id = {r.id: r for r in record.claim_results}
    assert by_id["auc"].status == "reproduced"
    assert by_id["auc"].observed == 0.9
    assert by_id["accuracy"].status == "reproduced"
    assert by_id["accuracy"].observed == 0.8


def test_run_reproduction_located_claim_escaping_repo_is_unverified_and_not_read(tmp_path):
    # A real file outside the repo dir, with a value that WOULD reproduce if read.
    outside_dir = tmp_path.parent / "outside_secret"
    outside_dir.mkdir(exist_ok=True)
    secret_file = outside_dir / "secret.json"
    secret_file.write_text(json.dumps({"model": {"auc": 0.9}}))

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    claims = [
        Claim(
            id="auc",
            value=0.9,
            tolerance=0.05,
            locator=Locator("../outside_secret/secret.json", "$.model.auc"),
        )
    ]
    record = run_reproduction(
        repo=str(repo_dir),
        run_command="echo run",
        claims=claims,
        executor=_noop_executor(),
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
    )
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "escapes the repo" in result.message


def test_run_reproduction_located_claim_nonzero_exit_is_unverified(tmp_path):
    _write_located(tmp_path, "out/summary.json", {"model": {"auc": 0.9}})
    claims = [Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "$.model.auc"))]
    record = _run(tmp_path, claims, _noop_executor(exit_code=1))
    result = record.claim_results[0]
    assert result.status == "unverified"
    assert result.observed is None
    assert "exit 1" in result.message
