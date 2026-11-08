"""Load the run bundle and optional tables into an assistant context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contig.assistant.models import Citation
from contig.bundle import verify_signature_in_dir
from contig.models import RunRecord, sha256_file
from contig.reporting.inputs import load_readiness_json, load_variants_json
from contig.workspace import bundle_dir_for, load_run


@dataclass
class Context:
    record: RunRecord
    bundle_dir: Path
    runs_dir: str
    variants: dict[str, Any] | None
    readiness: dict[str, Any] | None
    citations: dict[str, Citation]
    signature: dict[str, Any]


def _citation(label: str, path: Path, detail: str) -> Citation:
    return Citation(label=label, path=str(path), sha256=sha256_file(path), detail=detail)


def load_context(
    runs_dir: str | Path,
    run_id: str,
    *,
    variants_path: str | Path | None = None,
    readiness_path: str | Path | None = None,
) -> Context:
    record = load_run(runs_dir, run_id)
    bundle_dir = bundle_dir_for(runs_dir, run_id)
    record_path = bundle_dir / "run_record.json"

    citations = {
        "run_record": _citation("run_record", record_path, "Run record"),
    }
    variants = None
    if variants_path:
        variants = load_variants_json(variants_path)
        citations["variants"] = _citation("variants", Path(variants_path), "M1 variant evidence table")
    readiness = None
    if readiness_path:
        readiness = load_readiness_json(readiness_path)
        citations["readiness"] = _citation("readiness", Path(readiness_path), "M2 coverage/readiness table")

    return Context(
        record=record,
        bundle_dir=bundle_dir,
        runs_dir=str(runs_dir),
        variants=variants,
        readiness=readiness,
        citations=citations,
        signature=verify_signature_in_dir(bundle_dir),
    )
