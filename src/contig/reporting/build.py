"""Build, write, and check a research report."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from contig.bundle import verify_signature_in_dir
from contig.models import sha256_file
from contig.reporting.inputs import (
    input_record,
    load_readiness_json,
    load_run_bundle,
    load_variants_json,
    run_bundle_dir,
)
from contig.reporting.models import ReportMeta, ReportSpec
from contig.reporting.render import render_html


def _contig_version() -> str:
    try:
        return pkg_version("contig")
    except PackageNotFoundError:
        return "unknown"


def build_report(
    runs_dir: str | Path,
    run_id: str,
    spec: ReportSpec | None = None,
    *,
    variants_path: str | Path | None = None,
    readiness_path: str | Path | None = None,
) -> tuple[str, ReportMeta]:
    spec = spec or ReportSpec()
    record = load_run_bundle(runs_dir, run_id)
    bundle_dir = run_bundle_dir(runs_dir, run_id)

    inputs = [input_record("run_record", bundle_dir / "run_record.json", "Run record")]
    variants = None
    if variants_path:
        variants = load_variants_json(variants_path)
        inputs.append(input_record("variants", variants_path, "M1 variant evidence table"))
    readiness = None
    if readiness_path:
        readiness = load_readiness_json(readiness_path)
        inputs.append(input_record("readiness", readiness_path, "M2 coverage/readiness table"))

    signature = verify_signature_in_dir(bundle_dir)
    html = render_html(
        record,
        spec,
        variants=variants,
        readiness=readiness,
        inputs=inputs,
        signature=signature,
    )
    meta = ReportMeta(
        run_id=run_id,
        contig_version=_contig_version(),
        spec=spec,
        inputs=inputs,
        html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        notes=[
            f"Template: {spec.template}",
            f"Variant table attached: {'yes' if variants is not None else 'no'}",
            f"Readiness table attached: {'yes' if readiness is not None else 'no'}",
        ],
    )
    return html, meta


def write_report(html: str, meta: ReportMeta, out_path: str | Path, meta_path: str | Path) -> None:
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    meta = meta.model_copy(update={"html_path": str(out_path)})
    meta_path = Path(meta_path)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")


def check_report(meta_path: str | Path) -> list[dict[str, str]]:
    meta_path = Path(meta_path)
    if not meta_path.is_file():
        raise FileNotFoundError(f"report sidecar not found: {meta_path}")
    meta = ReportMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    results: list[dict[str, str]] = []
    for item in meta.inputs:
        path = Path(item.path)
        if not path.is_absolute():
            path = meta_path.parent / path
        if not path.is_file():
            results.append({
                "kind": item.kind,
                "path": item.path,
                "status": "missing",
                "expected": item.sha256,
                "actual": "",
            })
            continue
        actual = sha256_file(path)
        results.append({
            "kind": item.kind,
            "path": item.path,
            "status": "current" if actual == item.sha256 else "stale",
            "expected": item.sha256,
            "actual": actual,
        })
    if meta.html_path:
        html_path = Path(meta.html_path)
        if not html_path.is_file():
            results.append({
                "kind": "html",
                "path": meta.html_path,
                "status": "missing",
                "expected": meta.html_sha256,
                "actual": "",
            })
        else:
            actual = sha256_file(html_path)
            results.append({
                "kind": "html",
                "path": meta.html_path,
                "status": "current" if actual == meta.html_sha256 else "stale",
                "expected": meta.html_sha256,
                "actual": actual,
            })
    return results
