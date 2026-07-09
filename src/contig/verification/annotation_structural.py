"""Deterministic structural verification that an annotation step ran correctly.

Germline/somatic variant calling can enable nf-core/sarek's annotation step
(VEP -> CSQ, SnpEff -> ANN). This module proves the annotation actually ran over
the call set: it reads the annotated VCF bytes and reports whether the annotation
INFO field is declared and present, and what fraction of records carry it.

Research-use only: it verifies the annotation EXECUTED, never what the annotation
MEANS. It emits no pathogenicity/clinical judgement. Missing annotation degrades
to UNVERIFIED (never a false pass); a partial annotation is at most WARN.
"""

from __future__ import annotations

import gzip
import os
from dataclasses import dataclass
from pathlib import Path

from contig.models import QCResult

_ANNOTATION_KEYS = ("CSQ", "ANN")  # VEP, SnpEff


@dataclass(frozen=True)
class AnnotationMetrics:
    """What the annotated VCF's bytes say about annotation coverage."""

    info_key: str | None  # "CSQ" | "ANN" | None (neither declared in header)
    total_records: int
    annotated_records: int


def _open_text(path: str | os.PathLike):
    """Open a VCF for text reading, transparently gunzipping a `.gz` path."""
    p = Path(path)
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt")
    return open(p)


def _declared_key(header_lines: list[str]) -> str | None:
    """Return the first annotation INFO key declared in the header, or None."""
    for key in _ANNOTATION_KEYS:
        needle = f"##INFO=<ID={key},"
        if any(line.startswith(needle) for line in header_lines):
            return key
    return None


def _record_has_key(info: str, key: str) -> bool:
    """True if an INFO column carries the annotation key (KEY=... token)."""
    return any(field.split("=", 1)[0] == key for field in info.split(";"))


def annotation_metrics(vcf_path: str | os.PathLike) -> AnnotationMetrics:
    """Stream an annotated VCF; return declared key + record counts.

    `info_key` is the header-declared annotation key (CSQ/ANN) or None. When the
    header declares no key we still fall back to sniffing the first data record's
    INFO, so a header-stripped-but-annotated VCF is not misread as un-annotated.
    """
    header_lines: list[str] = []
    key: str | None = None
    resolved = False
    total = 0
    annotated = 0

    with _open_text(vcf_path) as fh:
        for line in fh:
            if line.startswith("#"):
                header_lines.append(line)
                continue
            if not resolved:
                key = _declared_key(header_lines)
                resolved = True
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 8:
                continue
            info = cols[7]
            if key is None:
                # Header declared nothing; sniff the record for either key.
                for candidate in _ANNOTATION_KEYS:
                    if _record_has_key(info, candidate):
                        key = candidate
                        break
            total += 1
            if key is not None and _record_has_key(info, key):
                annotated += 1

    return AnnotationMetrics(info_key=key, total_records=total, annotated_records=annotated)


def evaluate_annotation_structural(vcf_path: str | os.PathLike) -> list[QCResult]:
    """Emit the annotation structural checks for an annotated VCF (capped at WARN).

    - annotation_present: the annotated VCF declares/carries an annotation field
      AND at least one record is annotated -> pass; otherwise unverified (never a
      false pass — no key means we cannot claim annotation ran).
    - annotation_complete: fraction of data records carrying the annotation field;
      1.0 -> pass, <1.0 -> warn (some variants left un-annotated), no records or no
      key -> unverified.
    """
    m = annotation_metrics(vcf_path)

    if m.info_key is None or m.annotated_records == 0:
        return [
            QCResult(
                check="annotation_present",
                status="unverified",
                message=(
                    "no annotation field (CSQ/ANN) found in the VCF; "
                    "cannot verify an annotation step ran"
                ),
                value=None,
                kind="structural",
            )
        ]

    results = [
        QCResult(
            check="annotation_present",
            status="pass",
            message=(
                f"annotation field {m.info_key} present on "
                f"{m.annotated_records}/{m.total_records} records"
            ),
            value=None,
            kind="structural",
        )
    ]

    if m.total_records == 0:
        fraction = None
        status = "unverified"
        message = "annotation declared but the VCF has no data records"
    else:
        fraction = m.annotated_records / m.total_records
        if fraction >= 1.0:
            status = "pass"
            message = f"all {m.total_records} records carry {m.info_key}"
        else:
            status = "warn"
            message = (
                f"{m.annotated_records}/{m.total_records} records carry "
                f"{m.info_key}; some variants were left un-annotated"
            )

    results.append(
        QCResult(
            check="annotation_complete",
            status=status,
            message=message,
            value=fraction,
            kind="structural",
        )
    )
    return results
