"""Seam tests for the injectable triage layer (`contig.triage`).

Pins, test-first: the `Triage`/`NullTriage` seam shape, the single whitelist
declaration (`PAYLOAD_WHITELIST`) and the payload builder's mutation control
(raw-read fields can never appear in a constructed payload), the env-gated
https-only transport with defensive parsing (Phase 2), and the degrade-to-Null
contract every failure mode shares. No network is ever touched: the module's
`_post_json` seam is monkeypatched throughout.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import json
import typing

import pytest

import contig.triage as triage
from contig.triage import (
    PAYLOAD_WHITELIST,
    NullTriage,
    Triage,
    TriageRequest,
    TriageResult,
    build_triage_payload,
)


# ---------------------------------------------------------------------------
# Phase 1: seam shape — Triage alias, TriageRequest, TriageResult, NullTriage
# ---------------------------------------------------------------------------


def test_triage_is_a_callable_alias_over_request_to_result() -> None:
    assert typing.get_origin(Triage) is collections.abc.Callable
    params, result = typing.get_args(Triage)
    assert params == [TriageRequest]
    assert result is TriageResult


def test_triage_request_dataclass_shape() -> None:
    names = {f.name for f in dataclasses.fields(TriageRequest)}
    assert names == {"run_id", "surface", "mode", "payload"}
    req = TriageRequest(
        run_id="run-1", surface="qc_anomaly", mode="shadow", payload={}
    )
    assert req.run_id == "run-1"
    assert req.surface == "qc_anomaly"
    assert req.mode == "shadow"
    assert req.payload == {}


def test_triage_result_dataclass_shape() -> None:
    names = {f.name for f in dataclasses.fields(TriageResult)}
    assert names == {"mode", "confidence", "items", "reason"}
    result = TriageResult(
        mode="shadow", confidence=0.9, items={"r:s:c": 0.9}, reason=None
    )
    assert result.mode == "shadow"
    assert result.confidence == 0.9
    assert result.items == {"r:s:c": 0.9}
    assert result.reason is None


def test_null_triage_is_pure_and_env_independent(monkeypatch) -> None:
    # NullTriage is the default seam: it must return the fixed "no triage"
    # result regardless of the request, the environment, or a configured key.
    monkeypatch.delenv("CONTIG_JEV_KEY", raising=False)
    monkeypatch.delenv("CONTIG_JEV_URL", raising=False)
    req = TriageRequest(
        run_id="run-1",
        surface="verify_concordance",
        mode="shadow",
        payload={"run": {"run_id": "run-1"}, "checks": []},
    )
    result = NullTriage(req)
    assert isinstance(result, TriageResult)
    assert result.mode == "null"
    assert result.confidence is None
    assert result.items == {}
    assert result.reason is None

    # The same call with a key present is byte-identical: env never consulted.
    monkeypatch.setenv("CONTIG_JEV_KEY", "super-secret-key-value")
    assert NullTriage(req) == result


# ---------------------------------------------------------------------------
# Phase 1: the single whitelist declaration
# ---------------------------------------------------------------------------


def test_payload_whitelist_declares_exactly_the_contract_keys() -> None:
    # The whitelist is ONE module declaration; any raw-read key added to a
    # constructed payload must first be added here (and fails this pin).
    assert PAYLOAD_WHITELIST["run"] == frozenset(
        {
            "run_id",
            "assay",
            "pipeline",
            "task_counts",
            "failed_tasks",
            "repair_attempts",
            "verdict",
            "files",
        }
    )
    assert PAYLOAD_WHITELIST["file"] == frozenset({"size", "sha256"})
    assert PAYLOAD_WHITELIST["check"] == frozenset(
        {"check", "kind", "status", "value", "expected_range"}
    )


def _sync_ok_run_meta() -> dict:
    return {
        "run_id": "run-abc-1",
        "assay": "rna-seq",
        "pipeline": "nf-core/rnaseq",
        "task_counts": 42,
        "failed_tasks": 2,
        "repair_attempts": 1,
        "verdict": "FAIL",
    }


def _sync_ok_checks() -> list[dict]:
    return [
        {
            "check": "insert_size_median",
            "kind": "metric",
            "status": "PASS",
            "value": 331.0,
            "expected_range": {"min": 250, "max": 500},
        },
        {
            "check": "mapping_rate",
            "kind": "metric",
            "status": "WARN",
            "value": 0.93,
        },
    ]


def test_build_triage_payload_emits_only_whitelisted_run_keys() -> None:
    run_meta = dict(_sync_ok_run_meta())
    run_meta.update(
        {
            "sample_id": "donor-42",
            "sample_name": "patient-7",
            "message": "raw log text",
            "log_path": "/var/log/contig/run.log",
            "api_key": "super-secret",
            "reads": ["/reads/a.fastq", "/reads/b.fastq"],
        }
    )
    payload = build_triage_payload(run_meta, _sync_ok_checks())
    assert set(payload["run"]) <= set(PAYLOAD_WHITELIST["run"])
    assert payload["run"]["run_id"] == "run-abc-1"
    assert payload["run"]["task_counts"] == 42
    assert payload["run"]["verdict"] == "FAIL"


def test_build_triage_payload_filters_non_numeric_check_values() -> None:
    checks = [
        {"check": "a", "kind": "metric", "status": "FAIL", "value": "0.93"},
        {"check": "b", "kind": "metric", "status": "FAIL", "value": True},
        {"check": "c", "kind": "metric", "status": "FAIL", "value": None},
        {"check": "d", "kind": "metric", "status": "FAIL", "value": 0.72},
    ]
    payload = build_triage_payload(_sync_ok_run_meta(), checks)
    emitted = [c for c in payload["checks"]]
    assert "value" not in emitted[0]
    assert "value" not in emitted[1]
    assert "value" not in emitted[2]
    assert emitted[3]["value"] == 0.72


def test_build_triage_payload_expected_range_is_numeric_only() -> None:
    checks = [
        {
            "check": "a",
            "kind": "metric",
            "status": "PASS",
            "value": 1.0,
            "expected_range": {"min": 250, "max": 500, "label": "base pairs"},
        },
        {
            "check": "b",
            "kind": "metric",
            "status": "PASS",
            "value": 1.0,
            "expected_range": {"min": 1.0, "max": "lots"},
        },
        {
            "check": "c",
            "kind": "metric",
            "status": "PASS",
            "value": 1.0,
            "expected_range": {"all": "text"},
        },
    ]
    payload = build_triage_payload(_sync_ok_run_meta(), checks)
    emitted = payload["checks"]
    assert emitted[0]["expected_range"] == {"min": 250, "max": 500}
    assert emitted[1]["expected_range"] == {"min": 1.0}
    assert "expected_range" not in emitted[2]


def test_build_triage_payload_forces_verbatim_string_metadata() -> None:
    run_meta = dict(_sync_ok_run_meta())
    run_meta["verdict"] = "CERTAINLY-FAIL-99"
    run_meta["run_id"] = "opaque-per-run-id-xyz"
    payload = build_triage_payload(run_meta, _sync_ok_checks())
    assert payload["run"]["verdict"] == "CERTAINLY-FAIL-99"
    assert payload["run"]["run_id"] == "opaque-per-run-id-xyz"


def test_build_triage_payload_returns_deterministic_shape() -> None:
    first = build_triage_payload(_sync_ok_run_meta(), _sync_ok_checks())
    second = build_triage_payload(_sync_ok_run_meta(), _sync_ok_checks())
    assert first == second
    assert set(first) == {"run", "checks"}
    assert [set(c) for c in first["checks"]] == [
        {"check", "kind", "status", "value", "expected_range"},
        {"check", "kind", "status", "value"},
    ]


# ---------------------------------------------------------------------------
# Phase 1: mutation control — raw-read markers never reach a constructed payload
# ---------------------------------------------------------------------------

_FORBIDDEN_TOKENS = (
    "fastq",
    "bam",
    "vcf",
    "path",
    "bytes",
    "reads",
    "sample",
    "message",
    "api_key",
    "secret",
)


def _assert_no_forbidden_tokens(payload: dict) -> None:
    serialized = json.dumps(payload).lower()
    for token in _FORBIDDEN_TOKENS:
        assert token not in serialized, f"forbidden token leaked: {token!r}"


def _poisoned_run_meta() -> dict:
    return {
        "run_id": "run-abc-1",
        "assay": "rna-seq",
        "pipeline": "nf-core/rnaseq",
        "task_counts": 42,
        "failed_tasks": 2,
        "repair_attempts": 1,
        "verdict": "FAIL",
        "files": [
            {"path": "/reads/x.fastq.gz", "size": 123456, "sha256": "a" * 64},
            {
                "path": "/bam/y.aligned.bam",
                "size": 654321,
                "sha256": "b" * 64,
                "bytes": b"ACGTACGT",
            },
            {"path": "/vcf/z.vcf.gz", "size": 999, "sha256": "c" * 64},
            {"path": "/reads/not-a-file.fastq"},  # no size/hash: not egressable
        ],
        "sample_id": "donor-42",
        "sample_name": "patient-7",
        "message": "raw log text with error signatures",
        "log_path": "/var/log/contig/run.log",
        "api_key": "super-secret",
        "reads": ["/reads/a.fastq", "/reads/b.fastq"],
    }


def _poisoned_checks() -> list[dict]:
    return [
        {
            "check": "insert_size_median",
            "kind": "metric",
            "status": "PASS",
            "value": 331.0,
            "expected_range": {"min": 250, "max": 500},
            "message": "raw log text from the check",
            "path": "/reads/x.fastq",
            "bytes": b"ACGTACGTACGT",
            "sample": "donor-42",
        },
        {
            "check": "coverage_rate",
            "kind": "metric",
            "status": "WARN",
            "value": 0.93,
            "vcf_path": "/vcf/z.vcf.gz",
            "reads": ["/reads/a.fastq", "/reads/b.fastq"],
        },
    ]


def test_mutation_control_raw_read_markers_never_in_payload() -> None:
    payload = build_triage_payload(_poisoned_run_meta(), _poisoned_checks())
    _assert_no_forbidden_tokens(payload)

    # The whitelisted file metadata survives; the path never does.
    files = payload["run"]["files"]
    assert {frozenset(f) for f in files} == {
        frozenset({"size", "sha256"}),
        frozenset({"size", "sha256"}),
        frozenset({"size", "sha256"}),
    }
    assert files[0]["size"] == 123456
    assert files[0]["sha256"] == "a" * 64
    # A file entry with no whitelisted metadata is dropped entirely.
    assert all("sha256" in f for f in files)

    checks = payload["checks"]
    assert {frozenset(c) for c in checks} == {
        frozenset({"check", "kind", "status", "value", "expected_range"}),
        frozenset({"check", "kind", "status", "value"}),
    }


def test_mutation_control_holds_sha256_and_sizes_only() -> None:
    payload = build_triage_payload(_poisoned_run_meta(), _poisoned_checks())
    for file_meta in payload["run"]["files"]:
        assert set(file_meta) <= {"size", "sha256"}
        assert isinstance(file_meta["size"], (int, float))
        assert isinstance(file_meta["sha256"], str)
        assert len(file_meta["sha256"]) == 64