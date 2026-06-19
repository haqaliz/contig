"""Contig command-line interface (skeleton).

This is intentionally a thin surface: it constructs and echoes execution
*intent* (see ARCHITECTURE §4.1) but does not yet drive Nextflow. The real
run-and-verify engine lands once the toolchain is wired up.
"""

from __future__ import annotations

from importlib.metadata import version as _pkg_version

import typer
from pydantic import ValidationError

from contig.models import ExecutionTarget

app = typer.Typer(help="Contig — agentic bioinformatics analyst.")


@app.callback()
def main() -> None:
    """Contig — agentic bioinformatics analyst."""


@app.command()
def version() -> None:
    """Print the installed Contig version."""
    typer.echo(_pkg_version("contig"))


@app.command()
def plan(
    work_dir: str = typer.Option(..., "--work-dir", help="Run working directory."),
    backend: str = typer.Option("local", "--backend", help="Execution backend."),
    container_runtime: str = typer.Option(
        "docker", "--container-runtime", help="Container runtime."
    ),
    pipeline: str = typer.Option(
        "nf-core/rnaseq", "--pipeline", help="Pipeline to run."
    ),
) -> None:
    """Construct and echo the execution plan (no run is performed)."""
    try:
        target = ExecutionTarget(
            backend=backend,
            container_runtime=container_runtime,
            work_dir=work_dir,
        )
    except ValidationError as exc:
        typer.echo(f"Invalid execution target: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(
        f"Plan: run {pipeline} on {target.backend} "
        f"using {target.container_runtime} (work_dir={target.work_dir})"
    )
