"""Build, write, and check a research report."""

from __future__ import annotations

import hashlib
import json
import os
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from contig.bundle import SIGNING_KEY_ENV, verify_signature_in_dir
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


def write_report(html: str, meta: ReportMeta, out_path: str | Path, meta_path: str | Path) -> Path | None:
    """Write the HTML and sidecar; sign the sidecar when CONTIG_SIGNING_KEY is set.

    The detached signature covers the sidecar's canonical JSON, so it binds the
    HTML hash, every input hash, the spec, and the reviewer block. Returns the
    signature path, or None for an unsigned report. An unsigned rewrite removes a
    stale signature from an earlier signed write, so a leftover sidecar can never
    keep vouching for different content.
    """
    out_path = Path(out_path).resolve()
    meta = meta.model_copy(update={"html_path": str(out_path)})
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
