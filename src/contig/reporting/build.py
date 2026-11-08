"""Build, write, and check a research report."""

from __future__ import annotations

import hashlib
import json
import os
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from contig.bundle import (
    SIGNING_KEY_ENV,
    compute_output_checksums,
    results_dir_for,
    verify_outputs,
    verify_signature_in_dir,
)
from contig.models import RunRecord, sha256_file
from contig.registry import assay_for_pipeline
from contig.reporting.inputs import (
    input_record,
    load_readiness_json,
    load_run_bundle,
    load_variants_json,
    run_bundle_dir,
)
from contig.reporting.models import ReportMeta, ReportSpec
from contig.reporting.render import render_html
from contig.signing import (
    canonical_sha256_from_raw,
    public_key_for,
    sign_raw,
    signing_available,
    verify_raw,
)


def _contig_version() -> str:
    try:
        return pkg_version("contig")
    except PackageNotFoundError:
        return "unknown"


def _normalize_build(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.lower().replace("_", "").replace("-", "").replace(".", "")
    if "grch38" in text or "hg38" in text:
        return "GRCh38"
    if "grch37" in text or "hg19" in text or "b37" in text:
        return "GRCh37"
    return None


def _run_build(record: RunRecord) -> str | None:
    identity = record.reference_identity
    return _normalize_build(identity.genome) if identity else None


def _gene_set(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str) and value}


def compatibility_warnings(
    record: RunRecord,
    variants: dict | None,
    readiness: dict | None,
) -> list[str]:
    """Honest pre-flight warnings for an attached table that may not match the run.

    Never blocks the report: the tables are still rendered and hashed, with the
    mismatch named in the HTML, the sidecar, and stderr. Only facts present in
    the artifacts are compared; an unknown build is not guessed.
    """
    warnings: list[str] = []
    assay = record.assay or assay_for_pipeline(record.pipeline)
    run_build = _run_build(record)
    variants_meta = variants.get("meta") if isinstance(variants, dict) else None
    variants_build = (
        _normalize_build(variants_meta.get("build"))
        if isinstance(variants_meta, dict)
        else None
    )
    if run_build and variants_build and run_build != variants_build:
        warnings.append(
            f"The run reference is {run_build} but the variant table is {variants_build}."
        )
    readiness_meta = readiness.get("meta") if isinstance(readiness, dict) else None
    readiness_build = (
        _normalize_build(readiness_meta.get("build"))
        if isinstance(readiness_meta, dict)
        else None
    )
    if run_build and readiness_build and run_build != readiness_build:
        warnings.append(
            f"The run reference is {run_build} but the readiness table is {readiness_build}."
        )
    if assay not in {"variant_calling", "somatic_variant_calling"} and (
        variants is not None or readiness is not None
    ):
        attached = []
        if variants is not None:
            attached.append("variant evidence")
        if readiness is not None:
            attached.append("readiness")
        warnings.append(
            f"The run assay is {assay or 'unknown'}; attached "
            f"{' and '.join(attached)} are DNA-oriented research tables."
        )
    filters = variants_meta.get("filters") if isinstance(variants_meta, dict) else None
    variant_genes = _gene_set(filters.get("genes")) if isinstance(filters, dict) else set()
    if variants and not variant_genes:
        rows = variants.get("variants")
        if isinstance(rows, list):
            variant_genes = {
                row.get("gene")
                for row in rows
                if isinstance(row, dict) and isinstance(row.get("gene"), str)
            }
    readiness_genes: set[str] = set()
    if isinstance(readiness, dict):
        readiness_genes = {
            gene.get("gene")
            for gene in readiness.get("genes") or []
            if isinstance(gene, dict) and isinstance(gene.get("gene"), str)
        }
        if not readiness_genes:
            for target in readiness.get("targets") or []:
                if not isinstance(target, dict):
                    continue
                inner = target.get("target")
                if isinstance(inner, dict) and isinstance(inner.get("gene"), str):
                    readiness_genes.add(inner["gene"])
    missing = sorted(variant_genes - readiness_genes)
    if variant_genes and readiness_genes and missing:
        warnings.append(
            "Variant genes not covered by the readiness table: "
            + ", ".join(missing)
            + "."
        )
    return warnings


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
    warnings = compatibility_warnings(record, variants, readiness)
    html = render_html(
        record,
        spec,
        variants=variants,
        readiness=readiness,
        inputs=inputs,
        signature=signature,
        warnings=warnings,
    )
    meta = ReportMeta(
        run_id=run_id,
        contig_version=_contig_version(),
        spec=spec,
        inputs=inputs,
        html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        warnings=warnings,
        notes=[
            f"Template: {spec.template}",
            f"Variant table attached: {'yes' if variants is not None else 'no'}",
            f"Readiness table attached: {'yes' if readiness is not None else 'no'}",
        ],
    )
    return html, meta


def write_report(
    html: str,
    meta: ReportMeta,
    out_path: str | Path,
    meta_path: str | Path,
    *,
    relative_paths: bool = False,
) -> Path | None:
    """Write the HTML and sidecar; sign the sidecar when CONTIG_SIGNING_KEY is set.

    The detached signature covers the sidecar's canonical JSON, so it binds the
    HTML hash, every input hash, the spec, and the reviewer block. Returns the
    signature path, or None for an unsigned report. An unsigned rewrite removes a
    stale signature from an earlier signed write, so a leftover sidecar can never
    keep vouching for different content. ``relative_paths`` records the HTML path
    relative to the sidecar (for a portable bundle) instead of absolute.
    """
    out_path = Path(out_path).resolve()
    html_record = out_path.name if relative_paths else str(out_path)
    meta = meta.model_copy(update={"html_path": html_record})
    meta_path = Path(meta_path)
    meta_text = meta.model_dump_json(indent=2)
    signature = _manifest_signature(meta_text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    meta_path.write_text(meta_text, encoding="utf-8")
    sig_path = signature_path(meta_path)
    if signature is None:
        if sig_path.exists():
            sig_path.unlink()
        return None
    sig_path.write_text(json.dumps(signature, indent=2), encoding="utf-8")
    return sig_path


def signature_path(meta_path: str | Path) -> Path:
    """The detached signature sidecar for a report manifest."""
    return Path(str(meta_path) + ".sig.json")


def _manifest_signature(meta_text: str) -> dict[str, object] | None:
    private_key = os.environ.get(SIGNING_KEY_ENV)
    if not private_key:
        return None
    return {
        "algo": "ed25519",
        "public_key": public_key_for(private_key),
        "signature": sign_raw(meta_text, private_key),
        "signed_sha256": canonical_sha256_from_raw(meta_text),
    }


def check_report_signature(meta_path: str | Path) -> dict[str, object]:
    """Verify the sidecar's detached signature without ever raising on bad bytes.

    Returns ``{"signed": False, ...}`` when there is no signature sidecar, and
    otherwise ``signed``/``ok``/``detail`` (plus ``public_key`` when readable).
    A tampered manifest, a wrong key, a malformed sidecar, or unavailable crypto
    all yield ``ok`` False, never a false pass.
    """
    meta_path = Path(meta_path)
    if not meta_path.is_file():
        raise FileNotFoundError(f"report sidecar not found: {meta_path}")
    sig_path = signature_path(meta_path)
    if not sig_path.is_file():
        return {"signed": False, "ok": False, "detail": "no signature sidecar"}
    raw = meta_path.read_text(encoding="utf-8")
    try:
        sidecar = json.loads(sig_path.read_text(encoding="utf-8"))
        signature = sidecar["signature"]
        public_key = sidecar["public_key"]
        signed_sha256 = sidecar.get("signed_sha256")
        if not (isinstance(signature, str) and isinstance(public_key, str)):
            raise ValueError("signature fields must be strings")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"signed": True, "ok": False, "detail": "malformed signature sidecar"}
    if not signing_available():
        return {
            "signed": True,
            "ok": False,
            "public_key": public_key,
            "detail": "cryptography is not installed",
        }
    ok = verify_raw(raw, signature, public_key)
    detail = "" if ok else "signature does not verify against the manifest"
    if ok and signed_sha256 is not None:
        if canonical_sha256_from_raw(raw) != signed_sha256:
            ok = False
            detail = "signed_sha256 does not match the manifest"
    return {
        "signed": True,
        "ok": ok,
        "public_key": public_key,
        "detail": detail,
    }


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _unverified(kind: str, path: str, note: str) -> dict[str, str]:
    return {
        "kind": kind,
        "path": path,
        "status": "unverified",
        "expected": "",
        "actual": "",
        "note": note,
    }


def check_report(
    meta_path: str | Path, *, base_dir: str | Path | None = None
) -> list[dict[str, str]]:
    meta_path = Path(meta_path)
    if not meta_path.is_file():
        raise FileNotFoundError(f"report sidecar not found: {meta_path}")
    meta = ReportMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    base = Path(base_dir).resolve() if base_dir else meta_path.parent
    results: list[dict[str, str]] = []
    for item in meta.inputs:
        path = _resolve_path(item.path, base)
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
        html_path = _resolve_path(meta.html_path, base)
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


def check_report_outputs(
    meta_path: str | Path, *, base_dir: str | Path | None = None
) -> list[dict[str, str]]:
    """Verify the run's recorded output checksums against the results directory.

    Resolves the run record from the sidecar's ``run_record`` input, then reuses
    the same drift check as ``contig verify``. An unrecorded output set is
    reported ``unverified`` (never a false pass), not as a failure.
    """
    meta_path = Path(meta_path)
    meta = ReportMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    base = Path(base_dir).resolve() if base_dir else meta_path.parent
    run_input = next((item for item in meta.inputs if item.kind == "run_record"), None)
    if run_input is None:
        return [_unverified("outputs", str(meta_path), "no run_record input")]
    run_path = _resolve_path(run_input.path, base)
    try:
        record = RunRecord.model_validate_json(run_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [_unverified("outputs", str(run_path), "run record unreadable")]
    results_dir = results_dir_for(record, run_path.parent, base_dir=base)
    if not record.output_checksums:
        return [
            _unverified(
                "outputs", str(results_dir), "no output checksums recorded"
            )
        ]
    current = compute_output_checksums(results_dir)
    drift = verify_outputs(record, results_dir)
    rows: list[dict[str, str]] = []
    for rel, expected in sorted(record.output_checksums.items()):
        path = results_dir / rel
        if rel in drift["missing"]:
            status, actual = "missing", ""
        elif rel in drift["changed"]:
            status, actual = "stale", current.get(rel, "")
        else:
            status, actual = "current", expected
        rows.append({
            "kind": "output",
            "path": str(path),
            "status": status,
            "expected": expected,
            "actual": actual,
        })
    return rows


def check_report_sources(
    meta_path: str | Path, *, base_dir: str | Path | None = None
) -> list[dict[str, str]]:
    """Verify the upstream sources recorded by attached M1/M2 tables.

    Relative source paths resolve against ``base_dir`` when given, else the
    table's own directory. A table with no recorded sources is ``unverified``.
    """
    meta_path = Path(meta_path)
    meta = ReportMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    base = Path(base_dir).resolve() if base_dir else meta_path.parent
    rows: list[dict[str, str]] = []
    for item in meta.inputs:
        if item.kind not in {"variants", "readiness"}:
            continue
        table_path = _resolve_path(item.path, base)
        try:
            payload = json.loads(table_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows.append(
                _unverified(f"{item.kind}:sources", str(table_path), "table unreadable")
            )
            continue
        meta_payload = payload.get("meta") if isinstance(payload, dict) else None
        sources = meta_payload.get("sources", []) if isinstance(meta_payload, dict) else []
        if not isinstance(sources, list) or not sources:
            rows.append(
                _unverified(
                    f"{item.kind}:sources",
                    str(table_path),
                    "no upstream sources recorded",
                )
            )
            continue
        table_base = Path(base_dir).resolve() if base_dir else table_path.parent
        for source in sources:
            if not isinstance(source, dict):
                continue
            source_path = _resolve_path(str(source.get("path", "")), table_base)
            expected = str(source.get("sha256", ""))
            kind = f"{item.kind}:{source.get('kind', 'source')}"
            if not expected:
                rows.append(
                    _unverified(str(kind), str(source_path), "no sha256 recorded")
                )
                continue
            if not source_path.is_file():
                status, actual = "missing", ""
            else:
                actual = sha256_file(source_path)
                status = "current" if actual == expected else "stale"
            rows.append({
                "kind": kind,
                "path": str(source_path),
                "status": status,
                "expected": expected,
                "actual": actual,
            })
    return rows
