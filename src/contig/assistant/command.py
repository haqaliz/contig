"""Thin command layer for `contig ask` and `contig ask-eval`."""

from __future__ import annotations

import typer

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
) -> None:
    typer.echo(RESEARCH_USE_NOTICE, err=True)
    context = load_context(runs_dir, run_id, variants_path=variants, readiness_path=readiness)
    answer = answer_question(context, question)
    if llm:
        answer = paraphrase(answer, HttpModelClient.from_env(), question)

    if json_out:
        typer.echo(answer.model_dump_json(indent=2))
        return
    _print_answer(answer)


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
