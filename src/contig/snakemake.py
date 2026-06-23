"""The Snakemake engine adapter (PRD contract B, ARCHITECTURE §4.2).

Snakemake is the second workflow engine behind Contig's Engine abstraction. This
module is the mirror of the Nextflow path in `contig.events` + the command builder
in `contig.runner`: it builds a typed `snakemake` argv, and ingests Snakemake's own
machine-readable `--stats` JSON into the same `TaskEvent` shape the RunRecord, the
verifier, the report, and the bundle already consume. The engine is thus swapped at
the adapter seam; nothing downstream special-cases Snakemake.

The command is always a typed argv, never a shell string built from user input, so
a Snakefile path or cores count can never become an injected command.
"""

from __future__ import annotations

import json
from pathlib import Path

from contig.models import TaskEvent


class SnakemakeError(RuntimeError):
    """A Snakemake artifact cannot be ingested (e.g. a malformed stats file)."""


def build_snakemake_command(*, snakefile: str, cores: int, run_dir: str) -> list[str]:
    """Construct the `snakemake` argv for a workflow, with stats capture wired in.

    `--stats <run_dir>/stats.json` is the machine-readable capture we ingest (the
    Snakemake analogue of Nextflow's `-with-trace`). `--directory` runs Snakemake
    with the run dir as its working directory, so its outputs and the stats file
    land beside the rest of the run's artifacts. The argv is typed, never a shell
    string.
    """
    stats_path = str(Path(run_dir) / "stats.json")
    return [
        "snakemake",
        "--snakefile",
        snakefile,
        "--cores",
        str(cores),
        "--directory",
        run_dir,
        "--stats",
        stats_path,
    ]


def parse_snakemake_stats_text(text: str) -> list[TaskEvent]:
    """Parse a Snakemake `--stats` JSON string into terminal task events.

    Snakemake's stats JSON carries a `rules` mapping (rule name -> timing). Each
    rule that ran is reduced to one COMPLETED `TaskEvent`: reaching the stats file
    means the rule produced its outputs, so exit is 0. A failed Snakemake run exits
    nonzero and the runner surfaces that as the failure; the stats here describe
    what completed. A malformed file is a loud error, never a silent empty parse.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise SnakemakeError(f"could not parse Snakemake stats JSON: {exc}") from exc
    rules = data.get("rules", {})
    if not isinstance(rules, dict):
        raise SnakemakeError("Snakemake stats JSON has no 'rules' mapping")
    events: list[TaskEvent] = []
    for rule_name in rules:
        events.append(
            TaskEvent(
                process=rule_name,
                status="COMPLETED",
                exit=0,
                name=rule_name,
            )
        )
    return events


def parse_snakemake_stats_file(path: str | Path) -> list[TaskEvent]:
    """Read a Snakemake stats file and parse it into terminal task events."""
    return parse_snakemake_stats_text(Path(path).read_text())
