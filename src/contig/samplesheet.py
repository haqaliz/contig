"""RNA-seq sample-sheet parsing and validation (nf-core/rnaseq layout)."""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel, ValidationError


class SampleRow(BaseModel):
    sample: str
    fastq_1: str
    fastq_2: str | None = None
    strandedness: str = "auto"


class SarekSampleRow(BaseModel):
    """A row of the nf-core/sarek tumor/normal sample sheet.

    Columns: patient, sample, status, lane, fastq_1, fastq_2 (fastq_2 optional).
    `status` is 0 (normal) or 1 (tumor); range is validated in
    `validate_somatic_samplesheet`, not here, so an out-of-range value produces a
    row-scoped issue rather than an opaque parse error.
    """

    patient: str
    sample: str
    status: int
    lane: str | None = None
    fastq_1: str
    fastq_2: str | None = None


def parse_samplesheet(path) -> list[SampleRow]:
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        for required in ("sample", "fastq_1"):
            if required not in fields:
                raise ValueError(
                    f"sample sheet is missing required column: {required!r}"
                )
        rows = []
        for raw in reader:
            rows.append(
                SampleRow(
                    sample=raw["sample"],
                    fastq_1=raw["fastq_1"],
                    fastq_2=raw.get("fastq_2") or None,
                    strandedness=raw.get("strandedness") or "auto",
                )
            )
    return rows


def validate_samplesheet(path) -> list[str]:
    base = Path(path).resolve().parent
    try:
        rows = parse_samplesheet(path)
    except ValueError as exc:
        return [str(exc)]
    issues: list[str] = []

    seen: set[str] = set()
    reported_dups: set[str] = set()
    for row in rows:
        if row.sample in seen and row.sample not in reported_dups:
            issues.append(f"duplicate sample name: {row.sample}")
            reported_dups.add(row.sample)
        seen.add(row.sample)

    for i, row in enumerate(rows, start=1):
        if not row.sample.strip():
            issues.append(f"row {i}: empty sample name")
        if not row.fastq_1.strip():
            issues.append(f"row {i} ({row.sample}): empty fastq_1")
        refs = [row.fastq_1]
        if row.fastq_2 is not None:
            refs.append(row.fastq_2)
        for ref in refs:
            if not (base / ref).exists():
                issues.append(f"row {i} ({row.sample}): FASTQ not found: {ref}")
    return issues


def parse_somatic_samplesheet(path) -> list[SarekSampleRow]:
    """Parse a sarek tumor/normal sample sheet.

    Required columns: patient, sample, status, fastq_1 (lane and fastq_2 are
    optional). Raises ValueError on a missing required column — mirroring
    `parse_samplesheet` — so `validate_somatic_samplesheet` can surface it as the
    specific missing-column issue (e.g. a germline-shaped sheet lacking `status`).
    """
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        for required in ("patient", "sample", "status", "fastq_1"):
            if required not in fields:
                raise ValueError(
                    f"sample sheet is missing required column: {required!r}"
                )
        rows = []
        for raw in reader:
            rows.append(
                SarekSampleRow(
                    patient=raw["patient"],
                    sample=raw["sample"],
                    status=raw["status"],
                    lane=raw.get("lane") or None,
                    fastq_1=raw["fastq_1"],
                    fastq_2=raw.get("fastq_2") or None,
                )
            )
    return rows


def validate_somatic_samplesheet(path) -> list[str]:
    """Validate a sarek tumor/normal sample sheet for the somatic assay.

    Returns a list of human-readable issues (empty == valid), mirroring
    `validate_samplesheet`'s contract so the CLI's existing refuse-and-exit block
    can print + exit. Rules:

    - required columns present (parse error surfaced as a missing-column issue);
    - every row's `status` is 0 (normal) or 1 (tumor);
    - referenced FASTQs exist (relative to the sheet, like the generic validator);
    - each patient with a tumor row (status 1) has a matched normal row (status 0)
      — an unpaired tumor / tumor-only patient is refused with a message pointing
      the user at germline variant calling. Multi-tumor per patient (relapse) is
      allowed as long as a normal is present.
    """
    base = Path(path).resolve().parent
    try:
        rows = parse_somatic_samplesheet(path)
    except (ValueError, ValidationError) as exc:
        return [str(exc)]
    issues: list[str] = []

    for i, row in enumerate(rows, start=1):
        if row.status not in (0, 1):
            issues.append(
                f"row {i} ({row.sample}): status must be 0 (normal) or 1 (tumor), "
                f"got {row.status}"
            )
        refs = [row.fastq_1]
        if row.fastq_2 is not None:
            refs.append(row.fastq_2)
        for ref in refs:
            if not (base / ref).exists():
                issues.append(f"row {i} ({row.sample}): FASTQ not found: {ref}")

    # Group by patient and require each tumor to have a matched normal. A patient
    # with tumor row(s) but no normal is an unpaired tumor — for the tumor/normal
    # somatic assay we refuse and point at germline, rather than silently running
    # a tumor sample against nothing.
    by_patient: dict[str, set[int]] = {}
    for row in rows:
        if row.status in (0, 1):
            by_patient.setdefault(row.patient, set()).add(row.status)
    for patient, statuses in by_patient.items():
        if 1 in statuses and 0 not in statuses:
            issues.append(
                f"patient {patient}: tumor sample(s) with no matched normal "
                f"(status 0). The somatic tumor/normal assay needs a matched "
                f"normal; for a tumor-only or single-sample run use germline "
                f"variant calling instead."
            )
    return issues


def fastq_paths(path) -> list[Path]:
    base = Path(path).resolve().parent
    rows = parse_samplesheet(path)
    paths: list[Path] = []
    for row in rows:
        paths.append((base / row.fastq_1).resolve())
        if row.fastq_2 is not None:
            paths.append((base / row.fastq_2).resolve())
    return paths
