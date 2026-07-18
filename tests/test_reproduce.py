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
# run_reproduction()
# ---------------------------------------------------------------------------


def _fake_executor(exit_code: int, results: dict | None, results_path: str = "results.json"):
    """Build a fake executor that writes `results` into `repo/results_path`
    (unless `results` is None, in which case no file is written) and returns
    `exit_code`. Mirrors the injected `Callable[[list[str], Path], int]` seam.
    """

    def executor(argv: list[str], repo: Path) -> int:
        if results is not None:
            (repo / results_path).write_text(json.dumps(results))
        return exit_code

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
        return 0

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
