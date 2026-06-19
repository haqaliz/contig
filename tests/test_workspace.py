"""Tests for the run-workspace locator (ARCHITECTURE §7).

A "runs directory" holds one subdirectory per run, named by run_id; a run is
bundled when its subdir contains a ``run_record.json``. These tests pin the
locator behaviors against real files on disk.
"""

from pathlib import Path

from contig.bundle import write_bundle
from contig.models import ExecutionTarget, RunRecord
import pytest

from contig.workspace import (
    RunNotFoundError,
    bundle_dir_for,
    list_run_ids,
    load_run,
)


def _minimal_record(run_id: str = "r1") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.14.0",
        target=ExecutionTarget(
            backend="local", container_runtime="docker", work_dir="w"
        ),
        input_checksums={"reads.fastq.gz": "a" * 64},
    )


def test_bundle_dir_for_joins_runs_dir_and_run_id():
    assert bundle_dir_for("runs", "r1") == Path("runs/r1")


def test_load_run_round_trips_a_written_bundle(tmp_path):
    record = _minimal_record("r1")
    write_bundle(record, bundle_dir_for(tmp_path, "r1"))

    assert load_run(tmp_path, "r1") == record


def test_load_run_raises_run_not_found_naming_the_run_id(tmp_path):
    with pytest.raises(RunNotFoundError, match="missing-run"):
        load_run(tmp_path, "missing-run")


def test_list_run_ids_returns_bundled_run_ids_sorted(tmp_path):
    for run_id in ("r3", "r1", "r2"):
        write_bundle(_minimal_record(run_id), bundle_dir_for(tmp_path, run_id))

    assert list_run_ids(tmp_path) == ["r1", "r2", "r3"]


def test_list_run_ids_skips_subdir_without_a_run_record(tmp_path):
    write_bundle(_minimal_record("r1"), bundle_dir_for(tmp_path, "r1"))
    (tmp_path / "not-a-run").mkdir()

    assert list_run_ids(tmp_path) == ["r1"]


def test_list_run_ids_returns_empty_for_missing_runs_dir(tmp_path):
    assert list_run_ids(tmp_path / "does-not-exist") == []
