"""Tests for the Snakemake engine adapter (PRD contract B).

Snakemake is the second workflow engine behind the Engine abstraction. The adapter
builds a typed `snakemake` command, runs it through the same executor injection as
Nextflow, and ingests Snakemake's own machine-readable stats into the same
TaskEvent shape, so a Snakemake run produces a RunRecord that verify, report, and
the bundle consume unchanged. No test runs a real `snakemake`.
"""

import json
from pathlib import Path

import pytest

from contig.snakemake import (
    SnakemakeError,
    build_snakemake_command,
    parse_snakemake_stats_file,
    parse_snakemake_stats_text,
)

# Snakemake's `--stats` JSON: per-rule and per-file timing. The shape we ingest is
# the `rules` mapping (rule name -> {mean-runtime, min-runtime, ...}) plus a
# `total_runtime`. A real run writes more keys; we read only what we need.
STATS_OK = json.dumps(
    {
        "total_runtime": 12.5,
        "rules": {
            "align": {"mean-runtime": 8.0, "min-runtime": 8.0, "max-runtime": 8.0},
            "count": {"mean-runtime": 4.5, "min-runtime": 4.5, "max-runtime": 4.5},
        },
        "files": {
            "results/aligned.bam": {"start-time": 0.0, "stop-time": 8.0, "duration": 8.0},
            "results/counts.tsv": {"start-time": 8.0, "stop-time": 12.5, "duration": 4.5},
        },
    }
)


def test_build_command_invokes_snakemake_with_snakefile():
    cmd = build_snakemake_command(snakefile="/wf/Snakefile", cores=4, run_dir="/runs/r1")
    assert cmd[0] == "snakemake"
    i = cmd.index("--snakefile")
    assert cmd[i + 1] == "/wf/Snakefile"


def test_build_command_sets_cores():
    cmd = build_snakemake_command(snakefile="/wf/Snakefile", cores=8, run_dir="/runs/r1")
    i = cmd.index("--cores")
    assert cmd[i + 1] == "8"


def test_build_command_writes_stats_into_run_dir():
    cmd = build_snakemake_command(snakefile="/wf/Snakefile", cores=4, run_dir="/runs/r1")
    i = cmd.index("--stats")
    assert cmd[i + 1] == "/runs/r1/stats.json"


def test_build_command_directs_snakemake_to_the_run_dir():
    cmd = build_snakemake_command(snakefile="/wf/Snakefile", cores=4, run_dir="/runs/r1")
    i = cmd.index("--directory")
    assert cmd[i + 1] == "/runs/r1"


def test_build_command_is_a_typed_argv_not_a_shell_string():
    cmd = build_snakemake_command(snakefile="/wf/Snakefile", cores=4, run_dir="/runs/r1")
    assert isinstance(cmd, list)
    assert all(isinstance(token, str) for token in cmd)


def test_parse_stats_emits_one_event_per_rule():
    events = parse_snakemake_stats_text(STATS_OK)
    processes = {e.process for e in events}
    assert processes == {"align", "count"}


def test_parse_stats_marks_rules_completed():
    events = parse_snakemake_stats_text(STATS_OK)
    assert all(e.status == "COMPLETED" for e in events)
    assert all(e.exit == 0 for e in events)
    assert all(not e.is_failure for e in events)


def test_parse_stats_of_empty_run_is_no_events():
    events = parse_snakemake_stats_text(json.dumps({"total_runtime": 0.0, "rules": {}}))
    assert events == []


def test_parse_stats_file_reads_from_disk(tmp_path):
    stats = tmp_path / "stats.json"
    stats.write_text(STATS_OK)
    events = parse_snakemake_stats_file(stats)
    assert len(events) == 2


def test_parse_stats_text_rejects_malformed_json():
    with pytest.raises(SnakemakeError):
        parse_snakemake_stats_text("{not json")


# --- the shipped example Snakefile round-trips through the runner ----------------
EXAMPLE_SNAKEFILE = Path(__file__).parent / "fixtures" / "example.smk"


def test_example_snakefile_exists_for_the_round_trip():
    assert EXAMPLE_SNAKEFILE.is_file()


def test_example_snakefile_drives_a_run_record(tmp_path):
    # The example Snakefile flows through build, capture, record, and bundle via
    # the runner. A fake executor stands in for `snakemake` (no test runs the real
    # engine), writing the stats JSON the example's two rules would produce.
    from contig.bundle import load_bundle
    from contig.models import ExecutionTarget
    from contig.runner import run_pipeline

    stats = json.dumps({"total_runtime": 0.2, "rules": {"align": {}, "count": {}, "all": {}}})

    def fake_snakemake(cmd, artifact_path):
        assert cmd[0] == "snakemake"
        Path(artifact_path).write_text(stats)
        return 0

    record = run_pipeline(
        pipeline=str(EXAMPLE_SNAKEFILE),
        revision="local",
        profiles=[],
        target=ExecutionTarget(
            backend="local", container_runtime="conda", work_dir=str(tmp_path / "w"),
            engine="snakemake",
        ),
        input_paths=[],
        runs_dir=tmp_path / "runs",
        run_id="example-snake",
        executor=fake_snakemake,
    )
    assert {e.process for e in record.events} == {"align", "count", "all"}
    assert load_bundle(tmp_path / "runs" / "example-snake") == record
