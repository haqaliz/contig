"""Build and render the coverage/readiness table."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from contig.models import sha256_file
from contig.readiness.caveats import load_caveats
from contig.readiness.depth import load_depth, run_samtools_depth
from contig.readiness.evaluate import evaluate_targets
from contig.readiness.models import (
    ReadinessMeta,
    ReadinessTable,
    ReadinessThresholds,
    SourceProvenance,
    TargetMetrics,
)
from contig.readiness.targets import load_bed_targets, load_gtf_targets

COLUMNS = [
    "target", "gene", "transcript", "exon", "chrom", "start", "end",
    "bases", "covered_bases", "mean_depth", "pct_20x", "pct_50x", "pct_100x",
    "zero_bases", "caveats", "readiness", "reason",
]

RESEARCH_USE_NOTICE = (
    "Research use only: readiness is a data-sufficiency check, not a clinical "
    "guarantee or a diagnosis."
)


def _contig_version() -> str:
    try:
        return pkg_version("contig")
    except PackageNotFoundError:
        return "unknown"


def _source(kind: str, path: str | Path, note: str) -> SourceProvenance:
    return SourceProvenance(kind=kind, path=str(path), sha256=sha256_file(path), note=note)


def build_readiness(
    depth: str | Path | None = None,
    *,
    bam: str | Path | None = None,
    reference: str | Path | None = None,
    samtools_bin: str = "samtools",
    bed: str | Path | None = None,
    gtf: str | Path | None = None,
    genes: set[str] | list[str] = (),
    caveats: str | Path | None = None,
    thresholds: ReadinessThresholds | None = None,
) -> ReadinessTable:
    if (depth is None) == (bam is None):
        raise ValueError("provide exactly one of --depth or --bam")
    if (bed is None) == (gtf is None):
        raise ValueError("provide exactly one of --bed or --gtf")
    if bam is not None and bed is None:
        raise ValueError("--bam requires --bed (samtools depth needs target intervals)")
    thresholds = thresholds or ReadinessThresholds()

    notes: list[str] = []
    if bam is not None:
        with tempfile.TemporaryDirectory(prefix="contig-depth-") as tmp:
            depth_path = Path(tmp) / "depth.tsv"
            run_samtools_depth(
                bam, bed, depth_path,
                reference=reference,
                samtools_bin=samtools_bin,
            )
            depths, depth_stats = load_depth(depth_path)
        sources = [
            _source("bam", bam, "samtools depth -a -b")
        ]
        if reference is not None:
            sources.append(_source("reference", reference, "samtools depth reference"))
        notes.append("depth computed with samtools depth")
    else:
        depths, depth_stats = load_depth(depth)
        sources = [
            _source(
                "depth",
                depth,
                f"{depth_stats.positions} positions"
                + (f"; {depth_stats.skipped} malformed lines skipped" if depth_stats.skipped else "")
                + (f"; {depth_stats.duplicates} duplicate positions" if depth_stats.duplicates else ""),
            )
        ]
    sources[0].note = (
        (sources[0].note or "")
        + f"; {depth_stats.positions} positions"
        + (f"; {depth_stats.skipped} malformed lines skipped" if depth_stats.skipped else "")
        + (f"; {depth_stats.duplicates} duplicate positions" if depth_stats.duplicates else "")
    ).strip("; ")

    if bed is not None:
        targets = load_bed_targets(bed)
        sources.append(_source("targets", bed, f"{len(targets)} BED targets"))
        notes.append(f"{len(targets)} target(s) from BED")
    else:
        targets = load_gtf_targets(gtf, genes)
        sources.append(_source("targets", gtf, f"{len(targets)} GTF exon targets"))
        notes.append(f"{len(targets)} target(s) from GTF")

    caveat_regions = []
    if caveats is not None:
        caveat_regions = load_caveats(caveats)
        sources.append(_source("caveats", caveats, f"{len(caveat_regions)} caveat regions"))

    rows = evaluate_targets(targets, depths, thresholds, caveat_regions)
    meta = ReadinessMeta(
        sources=sources,
        thresholds=thresholds,
        contig_version=_contig_version(),
        notes=notes,
    )
    return ReadinessTable(rows=rows, meta=meta)


def _pct(value: float) -> str:
    return f"{value * 100:.2f}"


def render_tsv(table: ReadinessTable) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in table.rows:
        values = [
            row.target.name,
            row.target.gene,
            row.target.transcript,
            row.target.exon,
            row.target.chrom,
            row.target.start,
            row.target.end,
            row.bases,
            row.covered_bases,
            f"{row.mean_depth:.2f}",
            _pct(row.pct_20x),
            _pct(row.pct_50x),
            _pct(row.pct_100x),
            row.zero_bases,
            "; ".join(row.caveats),
            row.readiness,
            row.reason,
        ]
        lines.append("\t".join(str(value) for value in values))
    return "\n".join(lines) + "\n"


def render_json(table: ReadinessTable) -> str:
    payload = {
        "meta": table.meta.model_dump(mode="json"),
        "targets": [asdict(row) for row in table.rows],
    }
    return json.dumps(payload, indent=2) + "\n"


def write_table(table: ReadinessTable, path: str | Path, *, as_json: bool = False) -> None:
    Path(path).write_text(render_json(table) if as_json else render_tsv(table), encoding="utf-8")


def summarize(rows: list[TargetMetrics]) -> dict[str, int]:
    counts = {"ready": 0, "caution": 0, "not-interpretable": 0}
    for row in rows:
        counts[row.readiness] = counts.get(row.readiness, 0) + 1
    return counts
