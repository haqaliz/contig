"""Seam tests for the injectable triage layer (`contig.triage`).

Pins, test-first: the `Triage`/`NullTriage` seam shape, the single whitelist
declaration (`PAYLOAD_WHITELIST`) and the payload builder's mutation control
(raw-read fields can never appear in a constructed payload), the env-gated
https-only transport against the REAL Jev systemone protocol (envelope
`{model, state, questions}`, Bearer auth, default endpoint
`https://api.typesafe.ai/v1/systemone`), and the degrade-to-Null contract
every failure mode shares. No network is ever touched: the module's
`_post_json` seam is monkeypatched throughout, and the transport itself is
asserted through a patched `urllib.request.urlopen`.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import json
import typing

import pytest

import contig.triage as triage
from contig.triage import (
    DEFAULT_JEV_ENDPOINT,
    JEV_MODEL_ENV,
    PAYLOAD_WHITELIST,
    NullTriage,
    Triage,
    TriageRequest,
    TriageResult,
    build_triage_payload,
)

# A canned, real-shape systemone reply: one `triage` score question with a
# 0-1 `score` and a 0-1 `confidence`.
_REAL_SHAPE_REPLY = json.dumps(
    {
        "answers": {"triage": {"type": "score", "score": 0.31, "confidence": 0.6}},
        "usage": {"total_tokens": 1},
    }
)


# ---------------------------------------------------------------------------
# Phase 1: seam shape — Triage alias, TriageRequest, TriageResult, NullTriage
# ---------------------------------------------------------------------------

# The env needed by the real seam in the tests below; the value is a test
# stand-in, never a real key.
TEST_KEY = "super-secret-key-value"
TEST_MODEL = "jev-1.13.0"


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
    monkeypatch.delenv(JEV_MODEL_ENV, raising=False)
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
    monkeypatch.setenv("CONTIG_JEV_KEY", TEST_KEY)
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
            "api_key": TEST_KEY,
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
        "api_key": TEST_KEY,
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
# Phase 2: the real systemone protocol constants
# ---------------------------------------------------------------------------


def test_default_jev_endpoint_is_the_pinned_systemone_url() -> None:
    assert DEFAULT_JEV_ENDPOINT == "https://api.typesafe.ai/v1/systemone"


def test_jev_model_env_names_contig_jev_model() -> None:
    assert JEV_MODEL_ENV == "CONTIG_JEV_MODEL"


def test_model_aliases_are_exactly_the_non_reproducible_short_names() -> None:
    assert triage._MODEL_ALIASES == frozenset({"jev", "system-one"})


# ---------------------------------------------------------------------------
# Phase 2: the pure request envelope builder (_build_systemone_request)
# ---------------------------------------------------------------------------


def test_build_systemone_request_emits_the_real_envelope() -> None:
    state = {"run": {"run_id": "run-abc-1"}, "checks": []}
    envelope = triage._build_systemone_request("jev-1.13.0", state)
    assert set(envelope) == {"model", "state", "questions"}
    assert envelope["model"] == "jev-1.13.0"
    assert envelope["state"] is state
    questions = envelope["questions"]
    assert set(questions) == {"triage"}
    question = questions["triage"]
    assert question["type"] == "score"
    assert isinstance(question["instructions"], str)
    assert question["instructions"].strip()
    criteria = question["criteria"]
    assert isinstance(criteria, list)
    assert len(criteria) == 2
    assert all(isinstance(level, str) and level.strip() for level in criteria)
    # Exactly two ordered levels, clean first: the score lands in [0, 1] by
    # construction, and level 0 is the clean pole (low score).
    assert criteria[0] != criteria[1]


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
        return _REAL_SHAPE_REPLY

    return fake_post_json


def _keyed_modeled_env(monkeypatch, *, url: str | None = None) -> None:
    monkeypatch.setenv("CONTIG_JEV_KEY", TEST_KEY)
    monkeypatch.setenv(JEV_MODEL_ENV, TEST_MODEL)
    if url is None:
        monkeypatch.delenv("CONTIG_JEV_URL", raising=False)
    else:
        monkeypatch.setenv("CONTIG_JEV_URL", url)
    monkeypatch.delenv("CONTIG_JEV_ALLOW_HTTP", raising=False)


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
# Phase 2: model gate — CONTIG_JEV_MODEL absent/blank/alias ⇒ Null, no request
# ---------------------------------------------------------------------------


def test_model_absent_returns_null_naming_the_env(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
    monkeypatch.delenv(JEV_MODEL_ENV, raising=False)
    calls: list = []
    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))

    result = triage.default_jev_triage(_request())

    assert result.mode == "null"
    assert result.confidence is None
    assert result.items == {}
    assert result.reason is not None
    assert JEV_MODEL_ENV in result.reason
    assert calls == []


def test_model_blank_returns_null_naming_the_env(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
    monkeypatch.setenv(JEV_MODEL_ENV, "   ")
    calls: list = []
    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))

    result = triage.default_jev_triage(_request())

    assert result.mode == "null"
    assert JEV_MODEL_ENV in result.reason
    assert calls == []


def test_model_alias_refused_and_full_id_accepted(monkeypatch) -> None:
    calls: list = []
    for alias in ("jev", "system-one"):
        _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
        monkeypatch.setenv(JEV_MODEL_ENV, alias)
        monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
        result = triage.default_jev_triage(_request())
        assert result.mode == "null"
        assert result.reason is not None
        assert "alias" in result.reason.lower()
        assert calls == []

    # A full id passes the gate and reaches the transport.
    _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
    result = triage.default_jev_triage(_request())
    assert result.mode == "shadow"
    assert result.reason is None
    assert calls and calls[0][1]["model"] == TEST_MODEL


# ---------------------------------------------------------------------------
# Phase 2: transport — https-only URL gate, default endpoint, localhost opt-out
# ---------------------------------------------------------------------------


def test_absent_url_env_uses_the_pinned_default_endpoint(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch)
    calls: list = []
    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))

    result = triage.default_jev_triage(_request())

    assert result.mode == "shadow"
    assert calls and calls[0][0] == DEFAULT_JEV_ENDPOINT


def test_url_env_overrides_the_default(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
    calls: list = []
    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))

    result = triage.default_jev_triage(_request())

    assert result.mode == "shadow"
    assert calls and calls[0][0] == "https://triage.example.com/v1"


def test_https_url_hits_transport_and_returns_result(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
    calls: list = []

    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
    result = triage.default_jev_triage(_request())

    assert result.mode == "shadow"
    assert result.confidence == 0.6
    assert result.items == {"run-abc-1:qc_anomaly:triage": 0.31}
    assert result.reason is None
    assert calls and calls[0][0] == "https://triage.example.com/v1"


def test_post_body_is_the_systemone_envelope(monkeypatch) -> None:
    # The body handed to the transport must be the REAL envelope: `model`,
    # `state` (exactly the whitelisted payload), and one `triage` score
    # question — never the bare payload.
    _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
    calls: list = []
    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))

    triage.default_jev_triage(_request())

    url, payload, kwargs = calls[0]
    assert set(payload) == {"model", "state", "questions"}
    assert payload["model"] == TEST_MODEL
    assert payload["state"] == _request().payload
    assert payload["questions"]["triage"]["type"] == "score"
    assert isinstance(
        payload["questions"]["triage"]["criteria"], list
    )
    assert len(payload["questions"]["triage"]["criteria"]) == 2
    assert kwargs["key"] == TEST_KEY


def test_non_https_url_refused_without_transport(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch, url="http://evil.example/triage")
    calls: list = []

    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
    result = triage.default_jev_triage(_request())

    assert result.mode == "null"
    assert result.items == {}
    assert calls == []
    assert "http" in result.reason.lower()


def test_localhost_http_refused_without_opt_out(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch, url="http://localhost:8000/triage")
    calls: list = []

    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
    result = triage.default_jev_triage(_request())

    assert result.mode == "null"
    assert calls == []


def test_localhost_http_allowed_with_explicit_opt_out(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch, url="http://localhost:8000/triage")
    monkeypatch.setenv("CONTIG_JEV_ALLOW_HTTP", "1")
    calls: list = []

    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))
    result = triage.default_jev_triage(_request())

    assert result.mode == "shadow"
    assert calls and calls[0][0] == "http://localhost:8000/triage"


def test_garbage_url_refused_without_raise(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch)
    calls: list = []
    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))

    for url in ("http://", "https://", "not-a-url", "ftp://triage.example.com"):
        monkeypatch.setenv("CONTIG_JEV_URL", url)
        result = triage.default_jev_triage(_request())
        assert result.mode == "null"
        assert result.items == {}
        assert calls == []


# ---------------------------------------------------------------------------
# Phase 2: defense in depth — no state may egress with a key the whitelist
# does not name
# ---------------------------------------------------------------------------


def test_state_key_outside_whitelist_refuses_egress(monkeypatch) -> None:
    # Hand-built drift: a payload carrying a key the flat whitelist set does
    # not name must be refused BEFORE any transport call.
    _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
    calls: list = []
    monkeypatch.setattr(triage, "_post_json", _capturing_post_json(calls))

    drift_payloads = [
        {"run": {"run_id": "run-abc-1", "raw_reads": ["a.fastq"]}, "checks": []},
        {"run": {"run_id": "run-abc-1"}, "checks": [{"check": "a", "value": 1.0, "api_key": TEST_KEY}]},
        {"run": {"run_id": "run-abc-1"}, "checks": [], "sample_id": "donor-42"},
        {"run": {"run_id": "run-abc-1", "files": [{"path": "/reads/x.fastq"}]}, "checks": []},
    ]
    for state in drift_payloads:
        req = TriageRequest(
            run_id="run-abc-1", surface="qc_anomaly", mode="shadow", payload=state
        )
        result = triage.default_jev_triage(req)
        assert result.mode == "null"
        assert result.reason is not None
        assert "whitelist" in result.reason.lower()
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


def test_post_json_posts_envelope_with_bearer_key_and_content_type(monkeypatch) -> None:
    # The transport itself is pinned here: the constructed Request must carry
    # `Authorization: Bearer <key>` and `Content-Type: application/json`, POST
    # the envelope body, and respect the timeout.
    captured: dict = {}
    envelope = {"model": "jev-1.13.0", "state": {"run": {}, "checks": []}}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["method"] = request.method
        captured["url"] = request.full_url
        captured["body"] = request.data
        captured["authorization"] = request.get_header("Authorization")
        captured["content_type"] = request.get_header("Content-type")
        return _FakeResponse(b'{"answers": {}}\n')

    _patch_urlopen(monkeypatch, fake_urlopen)
    text = triage._post_json(
        "https://triage.example.com/v1",
        envelope,
        timeout=30,
        max_bytes=65536,
        key="super-secret-key-value",
    )

    assert text == '{"answers": {}}\n'
    assert captured["timeout"] == 30
    assert captured["method"] == "POST"
    assert captured["url"] == "https://triage.example.com/v1"
    assert captured["authorization"] == "Bearer super-secret-key-value"
    assert captured["content_type"] == "application/json"
    assert json.loads(captured["body"]) == envelope
    assert b"super-secret-key-value" not in captured["body"]


def test_post_json_requires_the_key_argument() -> None:
    with pytest.raises(TypeError):
        triage._post_json("https://triage.example.com/v1", {})  # type: ignore[call-arg]


def test_post_json_http_error_returns_none(monkeypatch) -> None:
    import urllib.error

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            "https://triage.example.com/v1", 500, "Internal Server Error", None, None
        )

    _patch_urlopen(monkeypatch, fake_urlopen)
    assert (
        triage._post_json(
            "https://triage.example.com/v1", {}, timeout=30, max_bytes=1024,
            key="k",
        )
        is None
    )


def test_post_json_urlerror_returns_none(monkeypatch) -> None:
    import urllib.error

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    _patch_urlopen(monkeypatch, fake_urlopen)
    assert (
        triage._post_json(
            "https://triage.example.com/v1", {}, timeout=30, max_bytes=1024,
            key="k",
        )
        is None
    )


def test_post_json_timeout_returns_none(monkeypatch) -> None:
    import socket

    def fake_urlopen(request, timeout):
        raise socket.timeout("timed out")

    _patch_urlopen(monkeypatch, fake_urlopen)
    assert (
        triage._post_json(
            "https://triage.example.com/v1", {}, timeout=30, max_bytes=1024,
            key="k",
        )
        is None
    )


def test_post_json_read_is_size_bounded(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return _FakeResponse(b"x" * (65536 + 1))

    _patch_urlopen(monkeypatch, fake_urlopen)
    text = triage._post_json(
        "https://triage.example.com/v1", {}, timeout=30, max_bytes=65536, key="k"
    )
    assert len(text) <= 65536 + 1  # a single read() is bounded


# ---------------------------------------------------------------------------
# Phase 2: degrade to Null on transport failure / oversized / malformed
# ---------------------------------------------------------------------------


def test_transport_failure_degrades_to_null(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
    monkeypatch.setattr(triage, "_post_json", lambda url, payload, **kw: None)

    result = triage.default_jev_triage(_request())
    assert result.mode == "null"
    assert result.confidence is None
    assert result.items == {}
    assert result.reason is not None


def test_oversized_response_degrades_to_null_with_oversized_reason(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
    monkeypatch.setattr(
        triage, "_post_json", lambda url, payload, **kw: "x" * (65536 + 1)
    )

    result = triage.default_jev_triage(_request())
    assert result.mode == "null"
    assert result.reason is not None
    assert "oversized" in result.reason.lower()


def test_malformed_response_degrades_to_null(monkeypatch) -> None:
    _keyed_modeled_env(monkeypatch, url="https://triage.example.com/v1")
    monkeypatch.setattr(triage, "_post_json", lambda url, payload, **kw: "not json {")

    result = triage.default_jev_triage(_request())
    assert result.mode == "null"
    assert result.items == {}
    assert result.reason is not None


# ---------------------------------------------------------------------------
# Phase 2: parse_triage_response — the real systemone reply, fail-closed
# ---------------------------------------------------------------------------


def test_parse_triage_response_returns_score_and_confidence() -> None:
    text = json.dumps(
        {
            "answers": {
                "triage": {"type": "score", "score": 0.4, "confidence": 0.8}
            },
            "usage": {"total_tokens": 5},
        }
    )
    assert triage.parse_triage_response(text) == (0.4, 0.8)


def test_parse_triage_response_accepts_integer_boundaries() -> None:
    text = json.dumps(
        {
            "answers": {
                "triage": {"type": "score", "score": 0, "confidence": 1}
            }
        }
    )
    assert triage.parse_triage_response(text) == (0.0, 1.0)


def test_parse_triage_response_error_key_returns_none() -> None:
    # `{"error": ...}` is the endpoint's decline, never a score.
    for text in (
        '{"error": "rate limited"}',
        '{"error": {"code": 429}, "answers": {"triage": {"score": 0.5, "confidence": 0.9}}}',
    ):
        assert triage.parse_triage_response(text) is None


def test_parse_triage_response_malformed_json_returns_none() -> None:
    for text in ("", "   ", "not json {", '{"answers": ['):
        assert triage.parse_triage_response(text) is None


def test_parse_triage_response_bad_shapes_return_none() -> None:
    for text in (
        "[]",
        '"hello"',
        "42",
        '{"not_answers": {}}',
        '{"answers": []}',
        '{"answers": {"not_triage": {"score": 0.5, "confidence": 0.9}}}',
        '{"answers": {"triage": []}}',
    ):
        assert triage.parse_triage_response(text) is None


def test_parse_triage_response_bad_score_returns_none() -> None:
    for score in (1.5, -0.1, "high", None, True, 2):
        text = json.dumps(
            {"answers": {"triage": {"score": score, "confidence": 0.5}}}
        )
        assert triage.parse_triage_response(text) is None


def test_parse_triage_response_bad_confidence_returns_none() -> None:
    for confidence in (2.0, -0.5, "low", None, False):
        text = json.dumps(
            {"answers": {"triage": {"score": 0.5, "confidence": confidence}}}
        )
        assert triage.parse_triage_response(text) is None


def test_parse_triage_response_never_raises_on_junk() -> None:
    for text in ("{", "]", "null", "2026-10-10", "\x00\xff", "x" * 100000):
        triage.parse_triage_response(text)


# ---------------------------------------------------------------------------
# Phase 2: the key never leaves the machine in any payload
# ---------------------------------------------------------------------------


def test_jev_key_name_never_in_any_constructed_payload() -> None:
    run_meta = dict(_sync_ok_run_meta())
    run_meta["CONTIG_JEV_KEY"] = TEST_KEY
    run_meta["api_key"] = "another-secret"
    checks = _sync_ok_checks()
    checks[0]["CONTIG_JEV_KEY"] = TEST_KEY

    payload = build_triage_payload(run_meta, checks)
    assert "CONTIG_JEV_KEY" not in json.dumps(payload)
    assert TEST_KEY not in json.dumps(payload)
    _assert_no_forbidden_tokens(payload)