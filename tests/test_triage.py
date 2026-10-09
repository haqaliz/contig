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


# ---------------------------------------------------------------------------
# Phase 2: env gate — CONTIG_JEV_KEY absent/empty ⇒ Null, no request constructed
# ---------------------------------------------------------------------------

# R6/R2: the constructed request is the observable; absent key ⇒ the seam
# must never build or send one (asserted on the _post_json hook).


def _request(mode: str = "shadow", surface: str = "qc_anomaly") -> TriageRequest:
    return TriageRequest(
        run_id="run-abc-1",
        surface=surface,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        payload=build_triage_payload(_sync_ok_run_meta(), _sync_ok_checks()),
    )


def _capturing_post_json(calls: list) -> object:
    def fake_post_json(url, payload, **kwargs):
        calls.append((url, payload, kwargs))
        return '{"items": []}'

    return fake_post_json


def test_key_absent_returns_null_and_post_json_never_called(monkeypatch) -> None:
    monkeypatch.delenv("CONTIG_JEV_KEY", raising=False)
    monkeypatch.delenv("CONTIG_JEV_URL", raising=False)
    calls: list = []

    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
    result = triage.default_jev_triage(_request())

    assert result.mode == "null"
    assert result.confidence is None
    assert result.items == {}
    assert result.reason is not None
    assert calls == []


def test_key_empty_returns_null_and_post_json_never_called(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_JEV_KEY", "")
    monkeypatch.delenv("CONTIG_JEV_URL", raising=False)
    calls: list = []

    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
    result = triage.default_jev_triage(_request())

    assert result.mode == "null"
    assert calls == []


# ---------------------------------------------------------------------------
# Phase 2: transport — https-only URL gate, localhost opt-out
# ---------------------------------------------------------------------------


def test_https_url_hits_transport_and_returns_result(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_JEV_KEY", "super-secret-key-value")
    monkeypatch.setenv("CONTIG_JEV_URL", "https://triage.example.com/v1")
    monkeypatch.delenv("CONTIG_JEV_ALLOW_HTTP", raising=False)
    calls: list = []

    def fake_post_json(url, payload, **kwargs):
        calls.append((url, payload, kwargs))
        return '{"items": [{"id": "run-abc-1:qc_anomaly:insert_size_median", "confidence": 0.9}]}'

    monkeypatch.setattr(triage, "_post_json", fake_post_json)
    result = triage.default_jev_triage(_request())

    assert result.mode == "shadow"
    assert result.confidence == 0.9
    assert result.items == {"run-abc-1:qc_anomaly:insert_size_median": 0.9}
    assert result.reason is None
    assert calls and calls[0][0] == "https://triage.example.com/v1"
    assert calls[0][1] == _request().payload


def test_non_https_url_refused_without_transport(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_JEV_KEY", "super-secret-key-value")
    monkeypatch.setenv("CONTIG_JEV_URL", "http://evil.example/triage")
    monkeypatch.delenv("CONTIG_JEV_ALLOW_HTTP", raising=False)
    calls: list = []

    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
    result = triage.default_jev_triage(_request())

    assert result.mode == "null"
    assert result.items == {}
    assert calls == []
    assert "http" in result.reason.lower()


def test_localhost_http_refused_without_opt_out(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_JEV_KEY", "super-secret-key-value")
    monkeypatch.setenv("CONTIG_JEV_URL", "http://localhost:8000/triage")
    monkeypatch.delenv("CONTIG_JEV_ALLOW_HTTP", raising=False)
    calls: list = []

    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
    result = triage.default_jev_triage(_request())

    assert result.mode == "null"
    assert calls == []


def test_localhost_http_allowed_with_explicit_opt_out(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_JEV_KEY", "super-secret-key-value")
    monkeypatch.setenv("CONTIG_JEV_URL", "http://localhost:8000/triage")
    monkeypatch.setenv("CONTIG_JEV_ALLOW_HTTP", "1")
    calls: list = []

    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
    result = triage.default_jev_triage(_request())

    assert result.mode == "shadow"
    assert calls and calls[0][0] == "http://localhost:8000/triage"


def test_garbage_url_refused_without_raise(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_JEV_KEY", "super-secret-key-value")
    monkeypatch.delenv("CONTIG_JEV_ALLOW_HTTP", raising=False)
    calls: list = []
    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))

    for url in ("http://", "https://", "not-a-url", "ftp://triage.example.com"):
        monkeypatch.setenv("CONTIG_JEV_URL", url)
        result = triage.default_jev_triage(_request())
        assert result.mode == "null"
        assert result.items == {}
        assert calls == []


# ---------------------------------------------------------------------------
# Phase 2: _post_json — the one network touch point, failure ⇒ None, never raises
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n: int = -1) -> bytes:
        return self._body[:n]


def _patch_urlopen(monkeypatch, fake):
    monkeypatch.setattr(triage.urllib.request, "urlopen", fake)


def test_post_json_posts_json_and_returns_raw_text(monkeypatch) -> None:
    captured: dict = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["method"] = request.method
        captured["url"] = request.full_url
        captured["body"] = request.data
        captured["content_type"] = request.get_header("Content-type")
        return _FakeResponse(b'{"items": []}\n')

    _patch_urlopen(monkeypatch, fake_urlopen)
    text = triage._post_json(
        "https://triage.example.com/v1",
        {"run": {}, "checks": []},
        timeout=30,
        max_bytes=65536,
    )

    assert text == '{"items": []}\n'
    assert captured["timeout"] == 30
    assert captured["method"] == "POST"
    assert captured["url"] == "https://triage.example.com/v1"
    assert captured["content_type"] == "application/json"
    assert b"CONTIG_JEV_KEY" not in captured["body"]


def test_post_json_http_error_returns_none(monkeypatch) -> None:
    import urllib.error

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            "https://triage.example.com/v1", 500, "Internal Server Error", None, None
        )

    _patch_urlopen(monkeypatch, fake_urlopen)
    assert (
        triage._post_json("https://triage.example.com/v1", {}, timeout=30, max_bytes=1024)
        is None
    )


def test_post_json_urlerror_returns_none(monkeypatch) -> None:
    import urllib.error

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    _patch_urlopen(monkeypatch, fake_urlopen)
    assert (
        triage._post_json("https://triage.example.com/v1", {}, timeout=30, max_bytes=1024)
        is None
    )


def test_post_json_timeout_returns_none(monkeypatch) -> None:
    import socket

    def fake_urlopen(request, timeout):
        raise socket.timeout("timed out")

    _patch_urlopen(monkeypatch, fake_urlopen)
    assert (
        triage._post_json("https://triage.example.com/v1", {}, timeout=30, max_bytes=1024)
        is None
    )


def test_post_json_read_is_size_bounded(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return _FakeResponse(b"x" * (65536 + 1))

    _patch_urlopen(monkeypatch, fake_urlopen)
    text = triage._post_json(
        "https://triage.example.com/v1", {}, timeout=30, max_bytes=65536
    )
    assert len(text) <= 65536 + 1  # a single read() is bounded


# ---------------------------------------------------------------------------
# Phase 2: degrade to Null on transport failure / oversized / malformed
# ---------------------------------------------------------------------------


def test_transport_failure_degrades_to_null(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_JEV_KEY", "super-secret-key-value")
    monkeypatch.setenv("CONTIG_JEV_URL", "https://triage.example.com/v1")
    monkeypatch.setattr(triage, "_post_json", lambda url, payload, **kw: None)

    result = triage.default_jev_triage(_request())
    assert result.mode == "null"
    assert result.confidence is None
    assert result.items == {}
    assert result.reason is not None


def test_oversized_response_degrades_to_null_with_oversized_reason(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_JEV_KEY", "super-secret-key-value")
    monkeypatch.setenv("CONTIG_JEV_URL", "https://triage.example.com/v1")
    monkeypatch.setattr(
        triage, "_post_json", lambda url, payload, **kw: "x" * (65536 + 1)
    )

    result = triage.default_jev_triage(_request())
    assert result.mode == "null"
    assert result.reason is not None
    assert "oversized" in result.reason.lower()


def test_malformed_response_degrades_to_null(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_JEV_KEY", "super-secret-key-value")
    monkeypatch.setenv("CONTIG_JEV_URL", "https://triage.example.com/v1")
    monkeypatch.setattr(triage, "_post_json", lambda url, payload, **kw: "not json {")

    result = triage.default_jev_triage(_request())
    assert result.mode == "null"
    assert result.items == {}
    assert result.reason is not None


# ---------------------------------------------------------------------------
# Phase 2: parse_triage_response — defensive, never raises
# ---------------------------------------------------------------------------


def test_parse_triage_response_accepts_valid_items_with_matching_ids() -> None:
    text = '{"items": [{"id": "run-abc-1:qc_anomaly:a", "confidence": 0.5}]}'
    items = triage.parse_triage_response(
        text, known_ids={"run-abc-1:qc_anomaly:a", "run-abc-1:qc_anomaly:b"}
    )
    assert items == {"run-abc-1:qc_anomaly:a": 0.5}


def test_parse_triage_response_malformed_json_returns_none() -> None:
    for text in ("", "   ", "not json {", '{"items": ['):
        assert triage.parse_triage_response(text, known_ids=set()) is None


def test_parse_triage_response_bad_shapes_return_none() -> None:
    for text in ("[]", '"hello"', "42", '{"not_items": []}', '{"items": {}}'):
        assert triage.parse_triage_response(text, known_ids=set()) is None


def test_parse_triage_response_unknown_ids_dropped() -> None:
    text = (
        '{"items": ['
        '{"id": "run-abc-1:qc_anomaly:known", "confidence": 0.5},'
        '{"id": "other:surface:unknown", "confidence": 0.9}'
        "]}"
    )
    items = triage.parse_triage_response(
        text, known_ids={"run-abc-1:qc_anomaly:known"}
    )
    assert items == {"run-abc-1:qc_anomaly:known": 0.5}


def test_parse_triage_response_bad_confidence_dropped() -> None:
    text = (
        '{"items": ['
        '{"id": "r:s:a", "confidence": 1.5},'
        '{"id": "r:s:b", "confidence": -0.1},'
        '{"id": "r:s:c", "confidence": "high"},'
        '{"id": "r:s:d", "confidence": null},'
        '{"id": "r:s:e", "confidence": 0.5}'
        "]}"
    )
    items = triage.parse_triage_response(text, known_ids={"r:s:a", "r:s:b", "r:s:c", "r:s:d", "r:s:e"})
    assert items == {"r:s:e": 0.5}


def test_parse_triage_response_never_raises_on_junk() -> None:
    for text in ("{", "]", "null", "2026-10-10", "\x00\xff", "x" * 100000):
        triage.parse_triage_response(text, known_ids=set())


# ---------------------------------------------------------------------------
# Phase 2: the key never leaves the machine in any payload
# ---------------------------------------------------------------------------


def test_jev_key_name_never_in_any_constructed_payload() -> None:
    run_meta = dict(_sync_ok_run_meta())
    run_meta["CONTIG_JEV_KEY"] = "super-secret-key-value"
    run_meta["api_key"] = "another-secret"
    checks = _sync_ok_checks()
    checks[0]["CONTIG_JEV_KEY"] = "super-secret-key-value"

    payload = build_triage_payload(run_meta, checks)
    assert "CONTIG_JEV_KEY" not in json.dumps(payload)
    assert "super-secret-key-value" not in json.dumps(payload)
    _assert_no_forbidden_tokens(payload)