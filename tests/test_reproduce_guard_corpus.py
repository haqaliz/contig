"""Corpus pins for the frozen reproduce scenario set (Phase D of guard-core).

The shipped `src/contig/data/reproduce_scenarios.jsonl` is the guarded corpus:
every line is one frozen replay through the REAL `run_reproduction` loop (real
load_claims, real classify, real locators, real freshness guard) with only the
executor/installer seams scripted. These tests pin the corpus's shape (unique
ids, family coverage, claim-id/expectation consistency, per-scenario observed
statuses) and its shipped evaluation numbers: the ONLY deliberate mismatch is
`known-miss`, so the committed baseline is 16/17 -- below 1.0, the guard's
liveness demonstration -- plus determinism and the baseline's corpus_sha.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from contig.models import sha256_file
from contig.reproduce_guard import (
    claim_family,
    default_reproduce_baseline_path,
    default_reproduce_scenarios_path,
    evaluate_reproduce,
    load_reproduce_baseline,
    load_reproduce_scenarios,
    run_reproduce_scenario,
)
from contig.verification.reproduce import load_claims

_RUN_START = 1_000_000.0  # repo-wide deterministic replay stamp

SCENARIOS_PATH = default_reproduce_scenarios_path()
BASELINE_PATH = default_reproduce_baseline_path()
FAMILIES = {"flat", "json", "table", "pattern", "notebook"}


def _shipped_scenarios():
    return load_reproduce_scenarios(SCENARIOS_PATH)


def _scenario_claim_ids(scenario) -> set[str]:
    with tempfile.TemporaryDirectory() as tmp:
        claims_path = Path(tmp) / "claims.json"
        claims_path.write_text(json.dumps(scenario.claims))
        return {c.id for c in load_claims(claims_path)}


def _replay_observed_statuses(scenario) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        record, _ = run_reproduce_scenario(
            scenario, repo_dir=Path(tmp), run_started_at=_RUN_START
        )
    return {r.id: r.status for r in record.claim_results}


def test_every_scenario_id_is_unique_and_seventeen_load():
    scenarios = _shipped_scenarios()
    ids = [s.scenario_id for s in scenarios]
    assert len(scenarios) == 17
    assert len(set(ids)) == len(ids)


def test_no_malformed_lines_in_the_corpus_file():
    # load_reproduce_scenarios silently skips malformed lines, so the raw line
    # count is pinned separately: 17 non-blank lines AND 17 parsed scenarios
    # proves no line was dropped.
    text = SCENARIOS_PATH.read_text()
    non_blank = [ln for ln in text.splitlines() if ln.strip()]
    assert len(non_blank) == 17


def test_every_locator_family_has_at_least_one_scenario():
    # Family derived through the real helpers (load_claims + claim_family), so
    # this also proves every inline claim passes the REAL schema validation.
    families = set()
    for scenario in _shipped_scenarios():
        with tempfile.TemporaryDirectory() as tmp:
            claims_path = Path(tmp) / "claims.json"
            claims_path.write_text(json.dumps(scenario.claims))
            for claim in load_claims(claims_path):
                families.add(claim_family(claim))
    assert families == FAMILIES


def test_expected_claim_statuses_keys_match_claim_ids_exactly():
    for scenario in _shipped_scenarios():
        ids = _scenario_claim_ids(scenario)
        assert set(scenario.expected_claim_statuses) == ids
        assert sorted(scenario.expected_claim_statuses) == sorted(ids)


def test_shipped_evaluation_only_known_miss_mismatches():
    report = evaluate_reproduce(_shipped_scenarios(), run_started_at=_RUN_START)
    assert report["matched_count"] == 16
    assert report["total_count"] == 17
    assert report["outcome_match_rate"] == pytest.approx(16 / 17)
    assert report["healed_count"] == 3
    assert report["recovery_rate"] == pytest.approx(3 / 17)
    assert report["covered_families"] == ["flat", "json", "notebook", "pattern", "table"]

    by_id = {r["scenario_id"]: r for r in report["scenario_results"]}
    mismatched = {sid: res for sid, res in by_id.items() if not res["matched"]}
    assert set(mismatched) == {"known-miss"}
    assert by_id["known-miss"]["mismatches"]["claim:c1"] == ("diverged", "reproduced")

    flat = report["per_family"]["flat"]
    assert (flat.matched, flat.total) == (11, 12)


def test_each_scenarios_observed_claim_status_matches_the_frozen_pin():
    # The per-scenario status table the baseline is frozen from. A classification
    # drift in classify/load_claims/locators flips one of these pins loudly.
    pins = {
        "flat-exact": {"c1": "reproduced"},
        "flat-within-tolerance": {"c1": "within_tolerance"},
        "flat-diverged": {"c1": "diverged"},
        "flat-non-finite": {"c1": "unverified"},
        "json-locator": {"c1": "reproduced"},
        "table-locator": {"c1": "within_tolerance"},
        "pattern-file": {"c1": "reproduced"},
        "pattern-stdout": {"c1": "reproduced"},
        "notebook-locator": {"c1": "reproduced"},
        "stale-artifact": {"c1": "unverified"},
        "env-resurrection-heal": {"c1": "reproduced"},
        "install-fail-giveup": {"c1": "unverified"},
        "nonzero-exit": {"c1": "unverified"},
        "known-miss": {"c1": "reproduced"},
        "env-alias-map-heal": {"claim-1": "reproduced"},
        "env-two-install-heal": {"claim-1": "reproduced"},
        "env-second-install-fail-giveup": {"claim-1": "unverified"},
    }
    for scenario in _shipped_scenarios():
        assert _replay_observed_statuses(scenario) == pins[scenario.scenario_id]


def test_baseline_corpus_sha_equals_scenarios_file_sha():
    baseline = load_reproduce_baseline(BASELINE_PATH)
    assert baseline is not None
    assert baseline.corpus_sha == sha256_file(SCENARIOS_PATH)
    assert baseline.scenario_count == 17
    assert baseline.outcome_match_rate == pytest.approx(16 / 17)
    assert baseline.recovery_rate == pytest.approx(3 / 17)


def test_evaluation_is_deterministic():
    first = evaluate_reproduce(_shipped_scenarios(), run_started_at=_RUN_START)
    second = evaluate_reproduce(_shipped_scenarios(), run_started_at=_RUN_START)
    assert first == second


def test_alias_scenario_mutation_control_flips_the_match():
    # Never-vacuous pin: env-alias-map-heal matches only because the replay
    # really resolves cv2 -> opencv-python AND records installed_and_retried.
    # Flipping its expected_repair must flip the scenario's match.
    scenarios = _shipped_scenarios()
    alias = next(s for s in scenarios if s.scenario_id == "env-alias-map-heal")
    by_id = {
        r["scenario_id"]: r
        for r in evaluate_reproduce(scenarios, run_started_at=_RUN_START)[
            "scenario_results"
        ]
    }
    assert by_id["env-alias-map-heal"]["matched"] is True

    mutated = [s for s in scenarios if s.scenario_id != "env-alias-map-heal"]
    mutated.append(alias.model_copy(update={"expected_repair": "retry_failed"}))
    mutated_by_id = {
        r["scenario_id"]: r
        for r in evaluate_reproduce(mutated, run_started_at=_RUN_START)[
            "scenario_results"
        ]
    }
    assert mutated_by_id["env-alias-map-heal"]["matched"] is False
    assert mutated_by_id["env-alias-map-heal"]["mismatches"]["repair"] == (
        "retry_failed",
        "installed_and_retried",
    )
