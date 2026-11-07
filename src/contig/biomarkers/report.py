"""Build and render the biomarker verification report."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from contig.biomarkers.models import (
    BiomarkerEntry,
    BiomarkerMeta,
    BiomarkerReport,
    SourceProvenance,
)
from contig.biomarkers.msi import MsiResult, msi_status
from contig.biomarkers.tmb import compute_tmb
from contig.models import sha256_file

COLUMNS = ["biomarker", "value", "unit", "status", "detail"]

RESEARCH_USE_NOTICE = (
    "Research use only: biomarker verification is a reproducibility check, not a "
    "clinical interpretation or treatment recommendation."
)


def _contig_version() -> str:
    try:
        return pkg_version("contig")
    except PackageNotFoundError:
        return "unknown"


def _source(kind: str, path: str | Path, note: str) -> SourceProvenance:
    return SourceProvenance(kind=kind, path=str(path), sha256=sha256_file(path), note=note)


def tmb_status(computed: float, reported: float | None, tolerance: float) -> tuple[str, float | None]:
    if reported is None:
        return "computed", None
    if reported <= 0:
        return "unverified", None
    delta = abs(computed - reported) / reported
    return ("match" if delta <= tolerance else "divergent"), delta


def build_report(
    vcf_path: str | Path,
    bed_path: str | Path,
    *,
    reported_tmb: float | None = None,
    tmb_tolerance: float = 0.20,
    reported_msi: str | None = None,
    reported_loh: str | None = None,
    reported_cnv: str | None = None,
    coding_only: bool = False,
    msi_result: MsiResult | None = None,
) -> BiomarkerReport:
    if not 0.0 <= tmb_tolerance <= 1.0:
        raise ValueError("tmb_tolerance must be between 0 and 1")
    result = compute_tmb(vcf_path, bed_path, coding_only=coding_only)
    computed = float(result["tmb"])
    status, delta = tmb_status(computed, reported_tmb, tmb_tolerance)

    entries = [
        BiomarkerEntry(
            name="TMB computed",
            value=f"{computed:.2f}",
            unit="mut/Mb",
            status=status,
            detail=(
                f"{result['definition']}; {result['variant_count']} variants / "
                f"{result['callable_mb']:.3f} Mb callable"
            ),
        )
    ]
    if reported_tmb is not None:
        entries.append(BiomarkerEntry(
            name="TMB reported",
            value=f"{reported_tmb:.2f}",
            unit="mut/Mb",
            status=status,
            detail=(
                f"relative delta {delta:.1%}" if delta is not None
                else "reported value was not comparable"
            ),
        ))

    if msi_result:
        entries.append(BiomarkerEntry(
            name="MSI",
            value=f"{msi_result.score:.2f}",
            unit="% unstable sites",
            status=msi_status(msi_result.status, reported_msi),
            detail=msi_result.detail,
        ))
    else:
        entries.append(BiomarkerEntry(
            name="MSI",
            value=reported_msi or "",
            status="not_verified",
            detail="no independent MSI caller or truth set attached",
        ))

    entries.extend([
        BiomarkerEntry(
            name="LOH",
            value=reported_loh or "",
            status="not_verified",
            detail="no independent LOH segments or truth set in v1",
        ),
        BiomarkerEntry(
            name="CNV",
            value=reported_cnv or "",
            status="not_verified",
            detail="no independent CNV segments or truth set in v1",
        ),
    ])

    sources = [
        _source("vcf", vcf_path, f"{result['records']} records"),
        _source("callable_bed", bed_path, f"{result['callable_mb']:.3f} Mb callable"),
    ]
    if msi_result:
        for kind, path in (
            ("msi_output", msi_result.output_path),
            ("msi_tumor_bam", msi_result.tumor_bam),
            ("msi_normal_bam", msi_result.normal_bam),
            ("msi_sites", msi_result.sites),
            ("msi_bed", msi_result.bed),
        ):
            if path and Path(path).is_file():
                sources.append(_source(kind, path, "MSI verification input"))
    meta = BiomarkerMeta(
        sources=sources,
        definition=str(result["definition"]),
        tolerance=tmb_tolerance,
        msi_threshold=msi_result.threshold if msi_result else None,
        contig_version=_contig_version(),
        notes=[
            f"{result['outside_count']} PASS variant(s) outside the callable BED",
            f"{result['unannotated_count']} unannotated variant(s) excluded by --coding-only"
            if coding_only else "",
            f"{result['skipped']} malformed VCF line(s) skipped" if result["skipped"] else "",
        ],
    )
    meta.notes = [note for note in meta.notes if note]
    return BiomarkerReport(entries=entries, meta=meta)


def render_tsv(report: BiomarkerReport) -> str:
    lines = ["\t".join(COLUMNS)]
    for entry in report.entries:
        lines.append("\t".join(str(value) for value in [entry.name, entry.value, entry.unit, entry.status, entry.detail]))
    return "\n".join(lines) + "\n"


def render_json(report: BiomarkerReport) -> str:
    payload = {
        "meta": report.meta.model_dump(mode="json"),
        "biomarkers": [entry.model_dump(mode="json") for entry in report.entries],
    }
    return json.dumps(payload, indent=2) + "\n"


def write_report(report: BiomarkerReport, path: str | Path, *, as_json: bool = False) -> None:
    Path(path).write_text(render_json(report) if as_json else render_tsv(report), encoding="utf-8")
