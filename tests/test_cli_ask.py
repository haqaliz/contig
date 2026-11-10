"""CLI smoke tests for `contig ask` and `contig ask-eval`."""

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from tests.ansi import plain

from contig.cli import app

FIX = Path(__file__).parent / "fixtures" / "reporting"
ASSIST = Path(__file__).parent / "fixtures" / "assistant"
RUNS = str(FIX / "runs")
VARIANTS = str(FIX / "variants.json")
READINESS = str(FIX / "readiness.json")
CASES = str(ASSIST / "eval.jsonl")


def _invoke(args, input=None):
    return CliRunner().invoke(app, args, input=input)


def test_ask_help_lists_options():
    result = _invoke(["ask", "--help"])
    assert result.exit_code == 0
    assert "--variants" in plain(result.output)
    assert "--readiness" in plain(result.output)
    assert "--llm" in plain(result.output)
    assert "--execute" in plain(result.output)
    assert "--approve-action" in plain(result.output)


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


def test_ask_execute_runs_an_approved_action(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "contig.assistant.actions.subprocess.run",
        lambda argv, check=False: calls.append(argv) or SimpleNamespace(returncode=0),
    )
    result = _invoke([
        "ask", "r1", "what is the verdict?", "--runs-dir", RUNS,
        "--execute", "1", "--approve-action",
    ])
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0][:2] == ["contig", "show"]
    assert "--explain" in calls[0]
    assert "Selected action:" in plain(result.output)
    assert "exited with code 0" in plain(result.output)


def test_ask_execute_prompts_and_can_refuse(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "contig.assistant.actions.subprocess.run",
        lambda argv, check=False: calls.append(argv) or SimpleNamespace(returncode=0),
    )
    result = _invoke(
        ["ask", "r1", "what is the verdict?", "--runs-dir", RUNS, "--execute", "1"],
        input="n\n",
    )
    assert result.exit_code == 0, result.output
    assert calls == []
    assert "Action not run." in plain(result.output)


def test_ask_execute_cannot_be_combined_with_json():
    result = _invoke([
        "ask", "r1", "what is the verdict?", "--runs-dir", RUNS,
        "--json", "--execute", "1", "--approve-action",
    ])
    assert result.exit_code == 1
    assert "cannot be combined" in plain(result.output)


def test_ask_execute_out_of_range_is_refused():
    result = _invoke([
        "ask", "r1", "what is the verdict?", "--runs-dir", RUNS,
        "--execute", "99", "--approve-action",
    ])
    assert result.exit_code == 1
    assert "between 1 and" in plain(result.output)


def test_ask_approve_action_requires_execute():
    result = _invoke([
        "ask", "r1", "what is the verdict?", "--runs-dir", RUNS,
        "--approve-action",
    ])
    assert result.exit_code == 1
    assert "requires --execute" in plain(result.output)


def test_ask_execute_propagates_a_failing_action(monkeypatch):
    monkeypatch.setattr(
        "contig.assistant.actions.subprocess.run",
        lambda argv, check=False: SimpleNamespace(returncode=3),
    )
    result = _invoke([
        "ask", "r1", "what is the verdict?", "--runs-dir", RUNS,
        "--execute", "1", "--approve-action",
    ])
    assert result.exit_code == 3
    assert "exited with code 3" in plain(result.output)


def test_ask_execute_prompt_approval_runs(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "contig.assistant.actions.subprocess.run",
        lambda argv, check=False: calls.append(argv) or SimpleNamespace(returncode=0),
    )
    result = _invoke(
        ["ask", "r1", "what is the verdict?", "--runs-dir", RUNS, "--execute", "1"],
        input="y\n",
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert "exited with code 0" in plain(result.output)
