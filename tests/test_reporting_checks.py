"""Tests for report-check's outputs, upstream sources, and --base-dir."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.cli import app
from contig.models import RunRecord, sha256_file
from contig.reporting.build import (
    build_report,
    check_report_outputs,
    check_report_sources,
    write_report,
)
from contig.reporting.models import ReportSpec

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"


def _record() -> RunRecord:
    return RunRecord.model_validate_json(
        (RUNS / "r1" / "run_record.json").read_text()
    )


def _runs_with_output(tmp_path: Path) -> tuple[Path, Path]:
    runs = tmp_path / "runs"
    bundle = runs / "r1"
    results = bundle / "results"
    results.mkdir(parents=True)
    out = results / "out.txt"
    out.write_text("result\n")
    record = _record().model_copy(
        update={"output_checksums": {"out.txt": sha256_file(out)}}
    )
    bundle.joinpath("run_record.json").write_text(record.model_dump_json(indent=2))
    return runs, out


def _write_sidecar(
    tmp_path: Path, *, variants_path: Path | None = None, runs: Path = RUNS
) -> Path:
    html, meta = build_report(
        runs, "r1", ReportSpec(), variants_path=variants_path or VARIANTS
    )
    sidecar = tmp_path / "report.json"
    write_report(html, meta, tmp_path / "report.html", sidecar)
    return sidecar


def _variants_with_source(tmp_path: Path, source: Path, path_value: str | None = None):
    payload = json.loads(VARIANTS.read_text())
    payload["meta"]["sources"] = [{
        "kind": "calls",
        "path": path_value or str(source),
        "sha256": sha256_file(source),
        "note": "test calls",
    }]
    table = tmp_path / "variants.json"
    table.write_text(json.dumps(payload))
    return table


def test_outputs_are_current_then_stale(tmp_path):
    runs, out = _runs_with_output(tmp_path)
    sidecar = _write_sidecar(tmp_path, runs=runs)
    current = check_report_outputs(sidecar)
    assert [row["status"] for row in current] == ["current"]
    out.write_text("tampered\n")
    stale = check_report_outputs(sidecar)
    assert [row["status"] for row in stale] == ["stale"]
    assert stale[0]["kind"] == "output"


def test_missing_output_is_reported(tmp_path):
    runs, out = _runs_with_output(tmp_path)
    sidecar = _write_sidecar(tmp_path, runs=runs)
    out.unlink()
    rows = check_report_outputs(sidecar)
    assert [row["status"] for row in rows] == ["missing"]


def test_outputs_without_recorded_checksums_are_unverified(tmp_path):
    runs = tmp_path / "runs"
    bundle = runs / "r1"
    bundle.mkdir(parents=True)
    record = _record().model_copy(update={"output_checksums": {}})
    bundle.joinpath("run_record.json").write_text(record.model_dump_json(indent=2))
    sidecar = _write_sidecar(tmp_path, runs=runs)
    rows = check_report_outputs(sidecar)
    assert [row["status"] for row in rows] == ["unverified"]


def test_sources_are_current_then_stale_and_missing(tmp_path):
    source = tmp_path / "calls.vcf"
    source.write_text("##fileformat=VCFv4.2\n")
    table = _variants_with_source(tmp_path, source)
    sidecar = _write_sidecar(tmp_path, variants_path=table)
    current = check_report_sources(sidecar)
    assert [row["status"] for row in current] == ["current"]
    assert current[0]["kind"] == "variants:calls"
    source.write_text("changed\n")
    assert [row["status"] for row in check_report_sources(sidecar)] == ["stale"]
    source.unlink()
    assert [row["status"] for row in check_report_sources(sidecar)] == ["missing"]


def test_sources_without_provenance_are_unverified(tmp_path):
    payload = json.loads(VARIANTS.read_text())
    payload["meta"]["sources"] = []
    table = tmp_path / "variants.json"
    table.write_text(json.dumps(payload))
    sidecar = _write_sidecar(tmp_path, variants_path=table)
    rows = check_report_sources(sidecar)
    assert [row["status"] for row in rows] == ["unverified"]


def test_sources_without_a_hash_are_unverified_not_missing(tmp_path):
    payload = json.loads(VARIANTS.read_text())
    payload["meta"]["sources"] = [{
        "kind": "gnomad_api",
        "path": "https://gnomad.broadinstitute.org/api",
        "sha256": "",
    }]
    table = tmp_path / "variants.json"
    table.write_text(json.dumps(payload))
    sidecar = _write_sidecar(tmp_path, variants_path=table)
    rows = check_report_sources(sidecar)
    assert [row["status"] for row in rows] == ["unverified"]


def test_base_dir_resolves_relative_source_paths(tmp_path):
    base = tmp_path / "base"
    (base / "data").mkdir(parents=True)
    source = base / "data" / "calls.vcf"
    source.write_text("##fileformat=VCFv4.2\n")
    tables = tmp_path / "tables"
    tables.mkdir()
    table = _variants_with_source(
        tables, source, path_value="data/calls.vcf"
    )
    sidecar = _write_sidecar(tmp_path, variants_path=table)
    assert [row["status"] for row in check_report_sources(sidecar)] == ["missing"]
    current = check_report_sources(sidecar, base_dir=base)
    assert [row["status"] for row in current] == ["current"]


def test_cli_checks_outputs_and_sources(tmp_path):
    runs, out = _runs_with_output(tmp_path)
    source = tmp_path / "calls.vcf"
    source.write_text("##fileformat=VCFv4.2\n")
    table = _variants_with_source(tmp_path, source)
    sidecar = _write_sidecar(tmp_path, variants_path=table, runs=runs)
    ok = CliRunner().invoke(
        app, ["report-check", str(sidecar), "--outputs", "--sources"]
    )
    assert ok.exit_code == 0, ok.output
    assert "output" in ok.output
    assert "variants:calls" in ok.output
    out.write_text("tampered\n")
    stale = CliRunner().invoke(
        app, ["report-check", str(sidecar), "--outputs", "--sources"]
    )
    assert stale.exit_code == 1
    assert "stale" in stale.output.lower()
