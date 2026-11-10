"""Tests for the assistant's approval-gated action execution."""

import pytest

from contig.assistant.actions import ActionError, execute_action, parse_action


def test_allowlisted_action_becomes_argv():
    assert parse_action("contig show r1 --runs-dir runs") == [
        "contig", "show", "r1", "--runs-dir", "runs",
    ]


@pytest.mark.parametrize(
    "command",
    [
        "",
        "rm -rf /",
        "contig run r1",
        "contig show r1; rm -rf /",
        "contig report r1 && echo ok",
        "contig variants <vcf> --json",
        "contig show r1 > out.txt",
        "contig report r1 | tee out.txt",
    ],
)
def test_unsafe_or_unknown_actions_are_refused(command):
    with pytest.raises(ActionError):
        parse_action(command)


def test_execution_requires_confirmation():
    calls = []
    ran, code = execute_action(
        "contig show r1",
        confirm=lambda prompt: False,
        runner=lambda argv: calls.append(argv) or 0,
    )
    assert ran is False
    assert code == 0
    assert calls == []


def test_missing_confirm_refuses_execution():
    calls = []
    ran, _ = execute_action(
        "contig show r1", runner=lambda argv: calls.append(argv) or 0
    )
    assert ran is False
    assert calls == []


def test_approved_action_runs_argv_without_a_shell():
    calls = []
    ran, code = execute_action(
        "contig report r1",
        approved=True,
        runner=lambda argv: calls.append(argv) or 0,
    )
    assert ran is True
    assert code == 0
    assert calls == [["contig", "report", "r1"]]


def test_nonzero_exit_is_returned():
    ran, code = execute_action(
        "contig verify r1", approved=True, runner=lambda argv: 7
    )
    assert ran is True
    assert code == 7


def test_missing_contig_executable_is_a_clear_error(monkeypatch):
    def missing(argv, check=False):
        raise FileNotFoundError("contig")

    monkeypatch.setattr("contig.assistant.actions.subprocess.run", missing)
    with pytest.raises(ActionError, match="could not run"):
        execute_action("contig show r1", approved=True)
