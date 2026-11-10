"""Thin command layer for `contig ask` and `contig ask-eval`."""

from __future__ import annotations

import typer

from contig.assistant.actions import execute_action
from contig.assistant.answer import answer_question
from contig.assistant.context import load_context
from contig.assistant.evaluate import evaluate_cases, load_eval_cases
from contig.assistant.llm import HttpModelClient, paraphrase

RESEARCH_USE_NOTICE = (
    "Research use only: answers come from this run bundle and the attached "
    "tables; they are not a clinical interpretation."
)


def _print_answer(answer) -> None:
    typer.echo(answer.answer)
    if answer.citations:
        typer.echo("")
        typer.echo("Sources:")
        for citation in answer.citations:
            typer.echo(f"- {citation.label}: {citation.path} (sha256 {citation.sha256})")
    if answer.actions:
        typer.echo("")
        typer.echo("Suggested actions:")
        for action in answer.actions:
            typer.echo(f"- {action}")


def run_ask(
    run_id: str,
    question: str,
    *,
    runs_dir: str = "runs",
    variants: str | None = None,
    readiness: str | None = None,
    json_out: bool = False,
    llm: bool = False,
    execute: int | None = None,
    approve_action: bool = False,
) -> None:
    if execute is not None and json_out:
        raise ValueError("--execute cannot be combined with --json")
    if approve_action and execute is None:
        raise ValueError("--approve-action requires --execute")
    typer.echo(RESEARCH_USE_NOTICE, err=True)
    context = load_context(runs_dir, run_id, variants_path=variants, readiness_path=readiness)
    answer = answer_question(context, question)
    if llm:
        answer = paraphrase(answer, HttpModelClient.from_env(), question)

    if json_out:
        typer.echo(answer.model_dump_json(indent=2))
        return
    _print_answer(answer)

    if execute is not None:
        if not answer.actions:
            raise ValueError("this answer has no suggested actions")
        if not 1 <= execute <= len(answer.actions):
            raise ValueError(
                f"--execute must be between 1 and {len(answer.actions)}"
            )
        command = answer.actions[execute - 1]
        typer.echo("")
        typer.echo(f"Selected action: {command}")
        ran, code = execute_action(
            command,
            approved=approve_action,
            confirm=lambda prompt: typer.confirm(prompt, default=False),
        )
        if not ran:
            typer.echo("Action not run.")
            return
        typer.echo(f"Action exited with code {code}.")
        if code != 0:
            raise typer.Exit(code=code)


def run_ask_eval(
    run_id: str,
    *,
    runs_dir: str = "runs",
    variants: str | None = None,
    readiness: str | None = None,
    cases: str,
    min_accuracy: float = 0.90,
) -> None:
    context = load_context(runs_dir, run_id, variants_path=variants, readiness_path=readiness)
    eval_cases = load_eval_cases(cases)
    report = evaluate_cases(context, eval_cases)
    typer.echo(
        f"ask-eval: {report.passed}/{report.total} passed "
        f"({report.accuracy:.1%}; threshold {min_accuracy:.0%})"
    )
    if report.misses:
        typer.echo("Misses:")
        for miss in report.misses:
            typer.echo(
                f"- {miss['question']!r}: expected {miss['expected_intent']} "
                f"from {miss['expected_source_kind'] or 'any source'}, "
                f"got {miss['actual_intent']} from {miss['actual_sources'] or 'no source'}"
            )
    if not report.exit_ok(min_accuracy):
        raise typer.Exit(code=1)
