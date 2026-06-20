"""RNA-seq sample-sheet parsing and validation (nf-core/rnaseq layout)."""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel


class SampleRow(BaseModel):
    sample: str
    fastq_1: str
    fastq_2: str | None = None
    strandedness: str = "auto"


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


def fastq_paths(path) -> list[Path]:
    base = Path(path).resolve().parent
    rows = parse_samplesheet(path)
    paths: list[Path] = []
    for row in rows:
        paths.append((base / row.fastq_1).resolve())
        if row.fastq_2 is not None:
            paths.append((base / row.fastq_2).resolve())
    return paths
