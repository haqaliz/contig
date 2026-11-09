"""CLI smoke tests for `contig ask` and `contig ask-eval`."""

import json
from pathlib import Path

from typer.testing import CliRunner

from tests.ansi import plain

from contig.cli import app

FIX = Path(__file__).parent / "fixtures" / "reporting"
ASSIST = Path(__file__).parent / "fixtures" / "assistant"
RUNS = str(FIX / "runs")
VARIANTS = str(FIX / "variants.json")
READINESS = str(FIX / "readiness.json")
CASES = str(ASSIST / "eval.jsonl")


def _invoke(args):
    return CliRunner().invoke(app, args)


def test_ask_help_lists_options():
    result = _invoke(["ask", "--help"])
    assert result.exit_code == 0
    assert "--variants" in plain(result.output)
    assert "--readiness" in plain(result.output)
    assert "--llm" in plain(result.output)


def test_ask_verdict_with_citations():
    result = _invoke([
        "ask", "r1", "what is the verdict?", "--runs-dir", RUNS,
        "--variants", VARIANTS, "--readiness", READINESS,
    ])
    assert result.exit_code == 0, result.output
    assert "WARN" in plain(result.output)
    assert "Sources:" in plain(result.output)
    assert "run_record" in plain(result.output)


def test_ask_json_output():
    result = _invoke([
        "ask", "r1", "what is the verdict?", "--runs-dir", RUNS,
        "--variants", VARIANTS, "--json",
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["intent"] == "verdict"
    assert payload["citations"][0]["label"] == "run_record"


def test_ask_unknown_refuses():
    result = _invoke(["ask", "r1", "what is the weather?", "--runs-dir", RUNS])
    assert result.exit_code == 0, result.output
    assert "won't guess" in plain(result.output)


def test_ask_eval_passes_the_fixture():
    result = _invoke([
        "ask-eval", "r1", "--runs-dir", RUNS, "--variants", VARIANTS,
        "--readiness", READINESS, "--cases", CASES, "--min-accuracy", "1.0",
    ])
    assert result.exit_code == 0, result.output
    assert "9/9" in plain(result.output)


def test_ask_eval_fails_below_threshold(tmp_path):
    wrong = tmp_path / "wrong.jsonl"
    wrong.write_text('{"question": "what is the verdict?", "expected_intent": "unknown"}\n')
    result = _invoke([
        "ask-eval", "r1", "--runs-dir", RUNS, "--cases", str(wrong),
        "--min-accuracy", "1.0",
    ])
    assert result.exit_code == 1
    assert "0/1" in plain(result.output)


def test_missing_run_exits_nonzero():
    result = _invoke(["ask", "missing", "what is the verdict?", "--runs-dir", RUNS])
    assert result.exit_code == 1
    assert "no bundled run" in plain(result.output).lower()


def test_llm_without_config_exits_nonzero(monkeypatch):
    monkeypatch.delenv("CONTIG_LLM_URL", raising=False)
    monkeypatch.delenv("CONTIG_LLM_MODEL", raising=False)
    result = _invoke([
        "ask", "r1", "what is the verdict?", "--runs-dir", RUNS, "--llm",
    ])
    assert result.exit_code == 1
    assert "no LLM configured" in plain(result.output)
