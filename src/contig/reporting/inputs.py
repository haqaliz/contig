"""Load the run bundle and optional M1/M2 JSON tables for a report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contig.models import RunRecord, sha256_file
from contig.reporting.models import ReportInput
from contig.workspace import bundle_dir_for, load_run


def load_run_bundle(runs_dir: str | Path, run_id: str) -> RunRecord:
    return load_run(runs_dir, run_id)


def run_bundle_dir(runs_dir: str | Path, run_id: str) -> Path:
    return bundle_dir_for(runs_dir, run_id)


def _load_json(path: str | Path, required: tuple[str, ...]) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"report input not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"report input is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"report input must be a JSON object: {path}")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"report input is missing {', '.join(missing)}: {path}")
    return payload


def load_variants_json(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path, ("meta", "variants"))
    if not isinstance(payload["variants"], list):
        raise ValueError(f"variants must be a list: {path}")
    return payload


def load_readiness_json(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path, ("meta", "targets"))
    if not isinstance(payload["targets"], list):
        raise ValueError(f"targets must be a list: {path}")
    return payload


def input_record(kind: str, path: str | Path, note: str | None = None) -> ReportInput:
    path = Path(path)
    return ReportInput(kind=kind, path=str(path), sha256=sha256_file(path), note=note)
