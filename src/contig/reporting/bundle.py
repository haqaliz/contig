"""Portable report bundles: HTML + sidecar + attached evidence tables."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from contig.bundle import verify_signature_in_dir
from contig.models import RunRecord
from contig.reporting.build import write_report
from contig.reporting.models import ReportMeta
from contig.reporting.render import render_html

BUNDLE_NOTE = "Portable bundle: sidecar paths are relative to this directory."


def _resolve(value: str, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def bundle_report(meta_path: str | Path, out_dir: str | Path) -> dict[str, object]:
    """Copy a report, its sidecar, and the attached tables into ``out_dir``.

    The copied sidecar records relative paths, so ``contig report-check`` works
    after the directory is moved. The HTML is re-rendered with those relative
    paths and a fresh hash; the attached tables keep every row, including rows
    beyond the HTML's ``max_rows`` cap. The run record (and its signature, when
    present) is copied too; the run's own outputs and upstream source files are
    not, so ``report-check --outputs/--sources`` still needs those.
    """
    meta_path = Path(meta_path)
    if not meta_path.is_file():
        raise FileNotFoundError(f"report sidecar not found: {meta_path}")
    meta = ReportMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    out = Path(out_dir)
    tables_dir = out / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    new_inputs = []
    record: RunRecord | None = None
    variants: dict | None = None
    readiness: dict | None = None
    for item in meta.inputs:
        source = _resolve(item.path, meta_path.parent)
        if not source.is_file():
            raise FileNotFoundError(f"report input not found: {source}")
        if item.kind == "run_record":
            dest = out / "run_record.json"
            shutil.copyfile(source, dest)
            run_signature = source.parent / "signature.json"
            if run_signature.is_file():
                shutil.copyfile(run_signature, out / "signature.json")
            record = RunRecord.model_validate_json(dest.read_text(encoding="utf-8"))
            relative = "run_record.json"
        elif item.kind in {"variants", "readiness"}:
            dest = tables_dir / f"{item.kind}.json"
            shutil.copyfile(source, dest)
            payload = json.loads(dest.read_text(encoding="utf-8"))
            if item.kind == "variants":
                variants = payload
            else:
                readiness = payload
            relative = f"tables/{item.kind}.json"
        else:
            dest = tables_dir / f"{item.kind}{source.suffix}"
            shutil.copyfile(source, dest)
            relative = f"tables/{dest.name}"
        new_inputs.append(item.model_copy(update={"path": relative}))

    if record is None:
        raise ValueError("report sidecar has no run_record input")
    html = render_html(
        record,
        meta.spec,
        variants=variants,
        readiness=readiness,
        inputs=new_inputs,
        signature=verify_signature_in_dir(out),
        warnings=meta.warnings,
    )
    bundled = meta.model_copy(
        update={
            "inputs": new_inputs,
            "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
            "notes": [*meta.notes, BUNDLE_NOTE],
        }
    )
    sig_path = write_report(
        html,
        bundled,
        out / "report.html",
        out / "report.json",
        relative_paths=True,
    )
    return {
        "out": str(out),
        "inputs": len(new_inputs),
        "signed": sig_path is not None,
    }
