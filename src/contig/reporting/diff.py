"""Diff two report sidecars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contig.reporting.models import ReportMeta


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flat: dict[str, Any] = {}
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flat.update(_flatten(item, path))
        return flat
    if isinstance(value, list):
        return {prefix: json.dumps(value, sort_keys=True)}
    return {prefix: value}


def diff_reports(a_path: str | Path, b_path: str | Path) -> dict[str, Any]:
    a_path, b_path = Path(a_path), Path(b_path)
    for path in (a_path, b_path):
        if not path.is_file():
            raise FileNotFoundError(f"report sidecar not found: {path}")
    a = ReportMeta.model_validate_json(a_path.read_text(encoding="utf-8"))
    b = ReportMeta.model_validate_json(b_path.read_text(encoding="utf-8"))

    left = _flatten({
        "run_id": a.run_id,
        "contig_version": a.contig_version,
        "spec": a.spec.model_dump(mode="json"),
        "inputs": [item.model_dump(mode="json") for item in a.inputs],
        "html_sha256": a.html_sha256,
        "notes": a.notes,
    })
    right = _flatten({
        "run_id": b.run_id,
        "contig_version": b.contig_version,
        "spec": b.spec.model_dump(mode="json"),
        "inputs": [item.model_dump(mode="json") for item in b.inputs],
        "html_sha256": b.html_sha256,
        "notes": b.notes,
    })

    changes = []
    for key in sorted(set(left) | set(right)):
        if left.get(key) != right.get(key):
            changes.append({"field": key, "a": left.get(key), "b": right.get(key)})
    return {"same": not changes, "changes": changes}


def render_diff(diff: dict[str, Any]) -> str:
    if diff["same"]:
        return "No differences.\n"
    lines = []
    for change in diff["changes"]:
        lines.append(f"{change['field']}:\n  a: {change['a']}\n  b: {change['b']}")
    return "\n".join(lines) + "\n"
