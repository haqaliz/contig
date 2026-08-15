"""Tests for the reproduce-case corpus core (C8 slice 2: capture/promote/scorer).

A `ReproduceCase` is built from a real `ReproduceRecord` (the gate decides when
a run earns a case), held pending until a human promotes it into the golden
corpus with expected labels, and re-derived by the scorer under the CURRENT
`classify` bands -- never from stored statuses. The load-bearing test is the
mutation control: a case stored with inputs that classify as "diverged" under
the shipped tolerance must FLIP to a mismatch under a mutated classifier with a
looser tolerance, proving the corpus stores inputs, not statuses.
"""

from __future__ import annotations

import pytest

from contig.models import (
    ClaimResult,
    Diagnosis,
    FamilyScore,
    RepairStep,
    ReproduceCase,
    ReproduceRecord,
)
from contig.reproduce_corpus import (
    append_reproduce_case,
    default_reproduce_corpus_history_path,
    default_reproduce_corpus_path,
    evaluate_reproduce_case,
    evaluate_reproduce_cases,
    load_reproduce_cases,
    promote_reproduce_case,
    reproduce_case_from_record,
    save_reproduce_cases,
    should_capture_reproduce,
    snapshot_from_reproduce_report,
)
from contig.verification.reproduce import Claim, NotebookLocator, classify

# Pinned deterministic identity (repo-wide convention, mirrors the
# reproduce-guard / env-resurrection fixtures).
_CLAIMS_SHA256 = "a" * 64
_CREATED_AT = "2026-07-18T00:00:00Z"
_REPRODUCE_ID = "rp_1"


def _claim_result(
    id_="c1",
    status="reproduced",
    claimed=0.9,
    observed=0.9,
    tolerance=0.02,
    delta=0.0,
):
    return ClaimResult(
        id=id_,
        status=status,
        claimed=claimed,
        observed=observed,
        tolerance=tolerance,
        delta=delta,
        message="ok",
    )


def _repair_step(outcome: str = "installed_and_retried") -> RepairStep:
    return RepairStep(
        attempt=1,
        diagnosis=Diagnosis(
            failure_class="missing_dependency",
            root_cause="module not installed",
            confidence=0.9,
        ),
        outcome=outcome,
        detail="installed and retried",
    )


def _record(**overrides) -> ReproduceRecord:
    base = dict(
        reproduce_id=_REPRODUCE_ID,
        repo="https://github.com/example/paper",
        run_command="python train.py --seed 0",
        claims_sha256=_CLAIMS_SHA256,
        claim_results=[_claim_result()],
        exit_code=0,
        created_at=_CREATED_AT,
    )
    base.update(overrides)
    return ReproduceRecord(**base)


def _claim(id_: str, locator=None, value: float = 0.9) -> Claim:
    return Claim(id=id_, value=value, tolerance=0.02, locator=locator)


# --- gate ---------------------------------------------------------------------


def test_capture_when_a_claim_diverged():
    record = _record(
        claim_results=[
            _claim_result(status="reproduced"),
            _claim_result(id_="c2", status="diverged", claimed=1.0, observed=1.5),
        ]
    )
    assert should_capture_reproduce(record) is True


def test_capture_when_claims_unverified():
    record = _record(
        claim_results=[
            _claim_result(status="unverified", observed=None),
        ]
    )
    assert should_capture_reproduce(record) is True


def test_capture_when_repair_history_non_empty():
    record = _record(claim_results=[_claim_result()], repair_history=[_repair_step()])
    assert should_capture_reproduce(record) is True


def test_capture_when_exit_code_nonzero():
    record = _record(exit_code=1)
    assert should_capture_reproduce(record) is True


def test_clean_run_is_not_captured():
    record = _record(
        claim_results=[
            _claim_result(status="reproduced"),
            _claim_result(
                id_="c2", status="within_tolerance", claimed=0.9, observed=0.91
            ),
        ]
    )
    assert should_capture_reproduce(record) is False


# --- builder ------------------------------------------------------------------


def test_builder_family_from_supplied_claims():
    claims = [
        _claim("c1"),
        _claim("c2", locator=NotebookLocator(source="out.ipynb", cell=0, pattern=r"([\d.]+)")),
    ]
    record = _record(
        claim_results=[
            _claim_result(id_="c1"),
            _claim_result(id_="c2"),
        ]
    )
    case = reproduce_case_from_record(record, claims=claims)
    assert [c.family for c in case.claims] == ["flat", "notebook"]


def test_builder_unknown_family_without_claims_list():
    case = reproduce_case_from_record(_record())
    assert case.claims[0].family == "unknown"


def test_builder_unknown_family_for_unmatched_claim_id():
    claims = [_claim("other")]
    case = reproduce_case_from_record(_record(), claims=claims)
    assert case.claims[0].family == "unknown"


def test_builder_repair_exit_description():
    record = _record(
        repair_history=[_repair_step("installed_and_retried")],
        exit_code=2,
    )
    case = reproduce_case_from_record(record)
    assert case.repair == "installed_and_retried"
    assert case.exit_code == 2
    assert "repair=installed_and_retried" in case.description
    assert "exit=2" in case.description


def test_builder_repair_none_when_no_history():
    case = reproduce_case_from_record(_record())
    assert case.repair is None


def test_builder_case_id_and_source_shapes():
    case = reproduce_case_from_record(_record())
    assert case.case_id == f"{_REPRODUCE_ID}-reproduce"
    assert case.source == f"pending:{_REPRODUCE_ID}"
    assert case.repo == "https://github.com/example/paper"
    assert case.run_command == "python train.py --seed 0"
    assert case.claims_sha256 == _CLAIMS_SHA256


# --- sidecar I/O ---------------------------------------------------------------


def test_append_load_round_trip(tmp_path):
    path = tmp_path / "cases.jsonl"
    case = reproduce_case_from_record(_record())
    append_reproduce_case(case, path)
    loaded = load_reproduce_cases(path)
    assert loaded == [case]
    assert loaded[0].model_dump_json() == case.model_dump_json()


def test_load_skips_blank_and_malformed_lines(tmp_path):
    path = tmp_path / "cases.jsonl"
    case = reproduce_case_from_record(_record())
    path.write_text(
        case.model_dump_json() + "\n\nnot-json\n{broken\n" + case.model_dump_json() + "\n"
    )
    loaded = load_reproduce_cases(path)
    assert loaded == [case, case]


def test_save_rewrites_whole_file(tmp_path):
    path = tmp_path / "cases.jsonl"
    append_reproduce_case(reproduce_case_from_record(_record()), path)
    case = reproduce_case_from_record(_record(reproduce_id="rp_2"))
    save_reproduce_cases([case], path)
    assert [c.case_id for c in load_reproduce_cases(path)] == ["rp_2-reproduce"]


# --- promote -------------------------------------------------------------------


def _pending_case(record: ReproduceRecord | None = None) -> ReproduceCase:
    return reproduce_case_from_record(record or _record())


def test_promote_moves_pending_to_golden_with_confirmed_source(tmp_path):
    pending_path = tmp_path / "pending.jsonl"
    golden_path = tmp_path / "golden.jsonl"
    append_reproduce_case(_pending_case(), pending_path)

    promote_reproduce_case(
        f"{_REPRODUCE_ID}-reproduce", pending_path=pending_path, golden_path=golden_path
    )

    golden = load_reproduce_cases(golden_path)
    assert len(golden) == 1
    assert golden[0].source == f"confirmed:{_REPRODUCE_ID}"
    assert golden[0].claims[0].expected_status is None
    assert load_reproduce_cases(pending_path) == []


def test_promote_label_less_keeps_expected_status_none(tmp_path):
    pending_path = tmp_path / "pending.jsonl"
    golden_path = tmp_path / "golden.jsonl"
    append_reproduce_case(_pending_case(), pending_path)

    promote_reproduce_case(
        f"{_REPRODUCE_ID}-reproduce", pending_path=pending_path, golden_path=golden_path
    )

    golden = load_reproduce_cases(golden_path)
    assert golden[0].claims[0].expected_status is None


def test_promote_applies_expected_claims(tmp_path):
    pending_path = tmp_path / "pending.jsonl"
    golden_path = tmp_path / "golden.jsonl"
    record = _record(
        claim_results=[
            _claim_result(id_="c1", status="reproduced"),
            _claim_result(id_="c2", status="diverged", claimed=1.0, observed=1.5),
        ]
    )
    append_reproduce_case(_pending_case(record), pending_path)

    promote_reproduce_case(
        f"{_REPRODUCE_ID}-reproduce",
        pending_path=pending_path,
        golden_path=golden_path,
        expected_claims={"c1": "reproduced", "c2": "diverged"},
    )

    golden = load_reproduce_cases(golden_path)
    by_id = {c.claim_id: c for c in golden[0].claims}
    assert by_id["c1"].expected_status == "reproduced"
    assert by_id["c2"].expected_status == "diverged"


def test_promote_unknown_claim_id_raises(tmp_path):
    pending_path = tmp_path / "pending.jsonl"
    golden_path = tmp_path / "golden.jsonl"
    append_reproduce_case(_pending_case(), pending_path)

    with pytest.raises(ValueError, match="no claim"):
        promote_reproduce_case(
            f"{_REPRODUCE_ID}-reproduce",
            pending_path=pending_path,
            golden_path=golden_path,
            expected_claims={"no-such": "reproduced"},
        )


def test_promote_unknown_pending_id_raises(tmp_path):
    pending_path = tmp_path / "pending.jsonl"
    golden_path = tmp_path / "golden.jsonl"
    append_reproduce_case(_pending_case(), pending_path)

    with pytest.raises(ValueError, match="no pending reproduce case"):
        promote_reproduce_case(
            "no-such-case", pending_path=pending_path, golden_path=golden_path
        )


def test_promote_duplicate_in_golden_raises(tmp_path):
    pending_path = tmp_path / "pending.jsonl"
    golden_path = tmp_path / "golden.jsonl"
    append_reproduce_case(_pending_case(), pending_path)
    append_reproduce_case(_pending_case(), golden_path)

    with pytest.raises(ValueError, match="already in the golden corpus"):
        promote_reproduce_case(
            f"{_REPRODUCE_ID}-reproduce", pending_path=pending_path, golden_path=golden_path
        )


def test_promote_bad_expected_repair_raises(tmp_path):
    pending_path = tmp_path / "pending.jsonl"
    golden_path = tmp_path / "golden.jsonl"
    append_reproduce_case(_pending_case(), pending_path)

    with pytest.raises(ValueError, match="repair"):
        promote_reproduce_case(
            f"{_REPRODUCE_ID}-reproduce",
            pending_path=pending_path,
            golden_path=golden_path,
            expected_repair="bogus",
        )


def test_promote_bad_expected_status_raises(tmp_path):
    pending_path = tmp_path / "pending.jsonl"
    golden_path = tmp_path / "golden.jsonl"
    append_reproduce_case(_pending_case(), pending_path)

    with pytest.raises(ValueError, match="status"):
        promote_reproduce_case(
            f"{_REPRODUCE_ID}-reproduce",
            pending_path=pending_path,
            golden_path=golden_path,
            expected_claims={"c1": "bogus"},
        )


def test_promote_sets_repair_and_exit_expectations(tmp_path):
    pending_path = tmp_path / "pending.jsonl"
    golden_path = tmp_path / "golden.jsonl"
    append_reproduce_case(_pending_case(), pending_path)

    promote_reproduce_case(
        f"{_REPRODUCE_ID}-reproduce",
        pending_path=pending_path,
        golden_path=golden_path,
        expected_repair="installed_and_retried",
        expected_exit_code=0,
    )

    golden = load_reproduce_cases(golden_path)
    assert golden[0].expected_repair == "installed_and_retried"
    assert golden[0].repair is None  # observed repair untouched by promote
    assert golden[0].expected_exit_code == 0


# --- scorer --------------------------------------------------------------------


def _labeled_case(**claim_overrides) -> ReproduceCase:
    record = _record(
        claim_results=[
            _claim_result(id_="c1", status="reproduced"),
            _claim_result(id_="c2", status="diverged", claimed=1.0, observed=1.5),
        ]
    )
    case = reproduce_case_from_record(record)
    by_id = {c.claim_id: c for c in case.claims}
    labels = {"c1": "reproduced", "c2": "diverged"}
    labels.update(claim_overrides)
    return case.model_copy(
        update={
            "claims": [
                c.model_copy(update={"expected_status": labels.get(c.claim_id)})
                for c in case.claims
            ]
        }
    )


def test_scorer_unlabeled_claims_excluded_from_rate():
    case = _labeled_case(c2=None)
    report = evaluate_reproduce_cases([case])
    assert report.total == 1  # only c1 is labeled
    assert report.correct == 1
    assert report.claim_match_rate == 1.0
    assert report.cases == 1


def test_scorer_correct_labels_match():
    case = _labeled_case()
    result = evaluate_reproduce_case(case)
    assert result.matched is True
    assert result.labeled_claims == 2
    assert result.matching_claims == 2
    assert result.divergence == []
    assert result.predicted_statuses == {"c1": "reproduced", "c2": "diverged"}


def test_scorer_wrong_label_mismatches_with_named_divergence():
    case = _labeled_case(c2="reproduced")
    result = evaluate_reproduce_case(case)
    assert result.matched is False
    assert result.matching_claims == 1
    assert result.divergence == [
        "c2: expected reproduced, re-derived diverged"
    ]


def test_scorer_expected_repair_mismatch_flips_matched():
    case = _labeled_case().model_copy(
        update={"repair": "none", "expected_repair": "installed_and_retried"}
    )
    result = evaluate_reproduce_case(case)
    assert result.matched is False
    assert any("repair" in d for d in result.divergence)


def test_scorer_expected_exit_code_mismatch_flips_matched():
    case = _labeled_case().model_copy(
        update={"exit_code": 0, "expected_exit_code": 1}
    )
    result = evaluate_reproduce_case(case)
    assert result.matched is False
    assert any("exit_code" in d for d in result.divergence)


def test_scorer_per_family_over_labeled_claims_only():
    claims = [
        _claim("c1"),
        _claim("c2", locator=NotebookLocator(source="out.ipynb", cell=0, pattern=r"([\d.]+)")),
    ]
    record = _record(
        claim_results=[
            _claim_result(id_="c1"),
            _claim_result(id_="c2"),
        ]
    )
    case = reproduce_case_from_record(record, claims=claims)
    by_id = {c.claim_id: c for c in case.claims}
    case = case.model_copy(
        update={
            "claims": [
                by_id["c1"].model_copy(update={"expected_status": "reproduced"}),
                by_id["c2"],  # unlabeled
            ]
        }
    )
    report = evaluate_reproduce_cases([case])
    assert report.per_family == {
        "flat": FamilyScore(matched=1, total=1, rate=1.0)
    }
    assert "notebook" not in report.per_family


def test_scorer_mismatches_are_labeled_cases_only():
    unlabeled = reproduce_case_from_record(_record())
    labeled = _labeled_case(c2="reproduced")
    report = evaluate_reproduce_cases([unlabeled, labeled])
    assert report.cases == 1
    assert len(report.mismatches) == 1
    assert report.mismatches[0].case_id == f"{_REPRODUCE_ID}-reproduce"


# --- mutation-control pin (the load-bearing test) ------------------------------


def test_mutation_control_looser_classifier_flips_stored_case():
    record = _record(
        claim_results=[
            _claim_result(
                id_="c1", status="diverged", claimed=1.0, observed=1.5, tolerance=0.1
            )
        ]
    )
    pending = reproduce_case_from_record(record)
    case = pending.model_copy(
        update={
            "claims": [
                c.model_copy(update={"expected_status": "diverged"})
                for c in pending.claims
            ]
        }
    )

    assert classify(1.0, 1.5, 0.1)[0] == "diverged"  # pin the shipped bands
    assert evaluate_reproduce_case(case).matched is True

    def loose_classifier(claimed, observed, tolerance):
        return classify(claimed, observed, tolerance * 10)

    assert classify(1.0, 1.5, 1.0)[0] == "within_tolerance"
    flipped = evaluate_reproduce_case(case, classifier=loose_classifier)
    assert flipped.matched is False
    assert "c1: expected diverged, re-derived within_tolerance" in flipped.divergence


# --- snapshot ------------------------------------------------------------------


def test_snapshot_from_report_mirrors_report(tmp_path):
    report = evaluate_reproduce_cases([_labeled_case()])
    snapshot = snapshot_from_reproduce_report(
        report,
        corpus_sha="c" * 64,
        timestamp=_CREATED_AT,
        contig_version="0.54.0",
    )
    assert snapshot.case_count == report.cases
    assert snapshot.claim_match_rate == report.claim_match_rate
    assert snapshot.per_family == report.per_family
    assert snapshot.corpus_sha == "c" * 64
    assert snapshot.timestamp == _CREATED_AT
    assert snapshot.contig_version == "0.54.0"


def test_snapshot_default_contig_version_none(tmp_path):
    report = evaluate_reproduce_cases([_labeled_case()])
    snapshot = snapshot_from_reproduce_report(
        report, corpus_sha="c" * 64, timestamp=_CREATED_AT
    )
    assert snapshot.contig_version is None
