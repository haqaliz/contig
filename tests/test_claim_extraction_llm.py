"""Tests for the OPTIONAL, env-gated LLM claim-extraction assist (aspect
`llm-assist` of reproduce-paper-claims).

Mirrors the `test_detect_llm.py` discipline exactly: the LLM assist is a pure
no-op unless a provider AND its key are configured; every test injects a FAKE
completion seam (monkeypatch of the module-local `_llm_complete`) so no test
makes a network call or touches a real API key. The real seam is shape-asserted
only (Phase 4) with a fake SDK module -- never executed against a provider.
"""

from __future__ import annotations

import json

import contig.verification.claim_extraction as claim_extraction
from contig.verification.claim_extraction import (
    ExtractedClaim,
    _claims_from_reply,
    extract_claims,
    extract_with_llm,
    merge_claims,
)


def _fake_completion(payload: object):
    """A fake seam returning a fixed model reply (str passthrough / JSON dump)."""

    def _complete(provider: str, prompt: str) -> str:
        return payload if isinstance(payload, str) else json.dumps(payload)

    return _complete


def _canned_claims() -> list[dict]:
    return [
        {"metric": "AUC", "value": 0.91, "unit": None, "source_text": "AUC of 0.91"},
        {
            "metric": "accuracy",
            "value": 87.0,
            "unit": "%",
            "source_text": "accuracy of 87%",
        },
    ]


# --- Phase 1: the env-gated seam ----------------------------------------------


def test_unconfigured_env_returns_empty_and_never_calls_seam(monkeypatch) -> None:
    monkeypatch.delenv("CONTIG_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    calls: list[tuple[str, str]] = []

    def _spy(provider: str, prompt: str) -> str:
        calls.append((provider, prompt))
        return "[]"

    monkeypatch.setattr(claim_extraction, "_llm_complete", _spy)

    assert extract_with_llm("AUC of 0.91 was achieved.") == []
    assert calls == []


def test_configured_env_calls_seam_once_with_provider_and_prompt(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    calls: list[tuple[str, str]] = []

    def _spy(provider: str, prompt: str) -> str:
        calls.append((provider, prompt))
        return json.dumps(_canned_claims())

    monkeypatch.setattr(claim_extraction, "_llm_complete", _spy)

    claims = extract_with_llm("AUC of 0.91; accuracy of 87%.")
    assert len(calls) == 1
    provider, prompt = calls[0]
    assert provider == "claude"
    assert "AUC of 0.91" in prompt  # the paper text is embedded in the prompt
    # the seam produced claims tagged as llm-origin
    assert all(isinstance(c, ExtractedClaim) for c in claims)
    assert all(c.origin == "llm" for c in claims)


# --- Phase 2: defensive reply parse (never raises) ----------------------------


def test_clean_json_list_parsed_into_llm_claims() -> None:
    claims = _claims_from_reply(json.dumps(_canned_claims()))
    assert [c.metric for c in claims] == ["AUC", "accuracy"]
    assert [c.value for c in claims] == [0.91, 87.0]
    assert [c.unit for c in claims] == [None, "%"]
    assert all(c.origin == "llm" for c in claims)
    # ids are the slug of the metric, uniquified within the reply
    assert [c.id for c in claims] == ["auc", "accuracy"]


def test_duplicate_metric_ids_are_uniquified_within_reply() -> None:
    reply = json.dumps(
        [
            {"metric": "AUC", "value": 0.91, "unit": None, "source_text": "a"},
            {"metric": "auc", "value": 0.88, "unit": None, "source_text": "b"},
        ]
    )
    ids = [c.id for c in _claims_from_reply(reply)]
    assert ids == ["auc", "auc_2"]


def test_prose_wrapped_json_list_is_tolerated() -> None:
    reply = (
        "Here are the claims I found:\n"
        + json.dumps(_canned_claims())
        + "\nHope this helps!"
    )
    claims = _claims_from_reply(reply)
    assert [c.metric for c in claims] == ["AUC", "accuracy"]


def test_not_json_returns_empty() -> None:
    assert _claims_from_reply("not json at all, sorry") == []


def test_json_object_not_a_list_returns_empty() -> None:
    assert _claims_from_reply(json.dumps({"metric": "AUC", "value": 0.91})) == []


def test_entry_missing_value_is_skipped() -> None:
    reply = json.dumps(
        [
            {"metric": "AUC", "unit": None, "source_text": "a"},  # no value
            {"metric": "accuracy", "value": 87.0, "unit": "%", "source_text": "b"},
        ]
    )
    claims = _claims_from_reply(reply)
    assert [c.metric for c in claims] == ["accuracy"]


def test_non_finite_and_bool_values_are_skipped() -> None:
    # NaN/Infinity (json allows them by default) and a bool value are all rejected
    reply = (
        '[{"metric": "a", "value": NaN, "source_text": "x"},'
        ' {"metric": "b", "value": Infinity, "source_text": "y"},'
        ' {"metric": "c", "value": true, "source_text": "z"},'
        ' {"metric": "d", "value": 0.5, "source_text": "w"}]'
    )
    claims = _claims_from_reply(reply)
    assert [c.metric for c in claims] == ["d"]


def test_seam_raising_degrades_to_empty(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def _boom(provider: str, prompt: str) -> str:
        raise RuntimeError("provider unreachable")

    monkeypatch.setattr(claim_extraction, "_llm_complete", _boom)
    assert extract_with_llm("AUC of 0.91.") == []


def test_missing_sdk_import_degrades_to_empty(monkeypatch) -> None:
    # Configured, but the lazy SDK import inside the real seam raises -> [].
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import builtins

    real_import = builtins.__import__

    def _no_anthropic(name, *args, **kwargs):
        if name == "anthropic":
            raise ModuleNotFoundError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_anthropic)
    assert extract_with_llm("AUC of 0.91.") == []


def test_api_key_never_leaks_into_output_or_log(monkeypatch, caplog) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "super-secret-key-value")
    monkeypatch.setattr(
        claim_extraction, "_llm_complete", _fake_completion(_canned_claims())
    )
    with caplog.at_level("DEBUG"):
        claims = extract_with_llm("AUC of 0.91; accuracy of 87%.")
    blob = " ".join(f"{c.id} {c.metric} {c.source_text}" for c in claims)
    assert "super-secret-key-value" not in blob
    assert "super-secret-key-value" not in caplog.text


# --- Phase 3: merge_claims (union deduped by (metric_slug, value), core wins) --


def _claim(id_: str, metric: str, value: float, origin: str) -> ExtractedClaim:
    return ExtractedClaim(id=id_, value=value, metric=metric, origin=origin)


def test_merge_core_wins_on_collision() -> None:
    core = [_claim("auc", "AUC", 0.91, "heuristic")]
    llm = [_claim("auc", "auc", 0.91, "llm")]  # same (slug, value)
    merged = merge_claims(core, llm)
    assert len(merged) == 1
    assert merged[0].origin == "heuristic"


def test_merge_appends_llm_only_claims_in_order() -> None:
    core = [_claim("auc", "AUC", 0.91, "heuristic")]
    llm = [
        _claim("auc", "auc", 0.91, "llm"),  # dup -> dropped
        _claim("f1", "F1", 0.8, "llm"),  # llm-only -> kept
        _claim("recall", "recall", 0.75, "llm"),  # llm-only -> kept
    ]
    merged = merge_claims(core, llm)
    assert [(c.metric, c.origin) for c in merged] == [
        ("AUC", "heuristic"),
        ("F1", "llm"),
        ("recall", "llm"),
    ]


def test_merge_reuniquifies_ids_across_the_merged_set() -> None:
    # core and an llm-only claim both slug to "auc" but differ in value ->
    # both kept, ids must be distinct after merge.
    core = [_claim("auc", "AUC", 0.91, "heuristic")]
    llm = [_claim("auc", "auc", 0.88, "llm")]
    merged = merge_claims(core, llm)
    ids = [c.id for c in merged]
    assert len(ids) == len(set(ids))  # all unique
    assert ids == ["auc", "auc_2"]


def test_merge_deduplicates_by_slug_and_value_not_by_id() -> None:
    # same metric+value but the llm gave a different id string; still a dup.
    core = [_claim("auc", "AUC", 0.91, "heuristic")]
    llm = [_claim("some_other_id", "auc", 0.91, "llm")]
    merged = merge_claims(core, llm)
    assert len(merged) == 1
    assert merged[0].origin == "heuristic"


def test_merge_is_deterministic_and_pure() -> None:
    core = [_claim("auc", "AUC", 0.91, "heuristic")]
    llm = [_claim("f1", "F1", 0.8, "llm")]
    first = merge_claims(core, llm)
    second = merge_claims(core, llm)
    assert [(c.id, c.metric, c.value, c.origin) for c in first] == [
        (c.id, c.metric, c.value, c.origin) for c in second
    ]
    # inputs untouched
    assert [c.id for c in core] == ["auc"]
    assert [c.id for c in llm] == ["f1"]


def test_merge_composes_real_core_and_llm_extractions(monkeypatch) -> None:
    # end-to-end: deterministic core + optional llm assist compose cleanly.
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    text = "The model reached an AUC of 0.91 on the held-out set."
    core = extract_claims(text)
    monkeypatch.setattr(
        claim_extraction,
        "_llm_complete",
        _fake_completion(
            [
                {"metric": "AUC", "value": 0.91, "unit": None, "source_text": "dup"},
                {"metric": "F1", "value": 0.8, "unit": None, "source_text": "F1 0.8"},
            ]
        ),
    )
    llm = extract_with_llm(text)
    merged = merge_claims(core, llm)
    metrics = [(c.metric, c.origin) for c in merged]
    assert ("AUC", "heuristic") in metrics  # core kept, llm dup dropped
    assert ("F1", "llm") in metrics  # llm-only appended
    assert len({c.id for c in merged}) == len(merged)  # ids unique


# --- Phase 4: real _llm_complete shape-asserted, NEVER executed against a net --
# The provider SDKs are not installed; we inject a FAKE module into sys.modules
# so the lazy `import` inside the real seam resolves to our recorder. This
# asserts the request the seam builds (model/max_tokens/messages) without any
# network call. This is the only test that exercises the real _llm_complete.


def test_real_seam_builds_claude_request_without_network(monkeypatch) -> None:
    import sys
    import types

    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "super-secret-key-value")

    captured: dict = {}

    class _Block:
        type = "text"
        text = "[]"

    class _Resp:
        content = [_Block()]

    class _Messages:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return _Resp()

    class _FakeAnthropic:
        def __init__(self, api_key: str) -> None:
            captured["api_key"] = api_key
            self.messages = _Messages()

    fake_mod = types.ModuleType("anthropic")
    fake_mod.Anthropic = _FakeAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)

    reply = claim_extraction._llm_complete("claude", "EXTRACT-PROMPT-BODY")

    assert reply == "[]"  # text blocks concatenated
    req = captured["request"]
    assert req["model"] == "claude-opus-4-8"
    assert isinstance(req["max_tokens"], int) and req["max_tokens"] > 0
    assert req["messages"] == [{"role": "user", "content": "EXTRACT-PROMPT-BODY"}]
    # the key is passed to the client but never appears in the built request
    assert captured["api_key"] == "super-secret-key-value"
    assert "super-secret-key-value" not in json.dumps(req)


def test_real_seam_builds_openai_request_without_network(monkeypatch) -> None:
    import sys
    import types

    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    captured: dict = {}

    class _Message:
        content = "[]"

    class _Choice:
        message = _Message()

    class _Resp:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return _Resp()

    class _Chat:
        def __init__(self) -> None:
            self.completions = _Completions()

    class _FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            captured["api_key"] = api_key
            self.chat = _Chat()

    fake_mod = types.ModuleType("openai")
    fake_mod.OpenAI = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_mod)

    reply = claim_extraction._llm_complete("openai", "EXTRACT-PROMPT-BODY")

    assert reply == "[]"
    req = captured["request"]
    assert req["model"] == "gpt-4o"
    assert req["messages"] == [{"role": "user", "content": "EXTRACT-PROMPT-BODY"}]
    assert captured["api_key"] == "test-key"


def test_claim_extraction_does_not_import_a_provider_sdk_at_module_top() -> None:
    # Guardrail: importing claim_extraction never pulls a provider SDK, and the
    # detect->claim_extraction edge is one-way (no import cycle).
    import sys

    assert "anthropic" not in sys.modules
    assert "openai" not in sys.modules
    import contig.detect as _detect

    assert "claim_extraction" not in _detect.__dict__  # detect does not import us
