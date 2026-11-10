"""Build and render the coverage/readiness table."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from contig.models import sha256_file
from contig.readiness.caveats import load_caveats
from contig.readiness.depth import load_depth, load_depth_for_targets, run_samtools_depth
from contig.readiness.evaluate import evaluate_targets, summarize_by_gene
from contig.readiness.models import (
    ReadinessMeta,
    ReadinessTable,
    ReadinessThresholds,
    SampleQC,
    SourceProvenance,
    TargetMetrics,
)
from contig.readiness.targets import load_bed_targets, load_gtf_targets
from contig.verification.sex_plausibility import sex_signals

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


SEX_ALIASES = {
    "xx": "XX",
    "female": "XX",
    "f": "XX",
    "2": "XX",
    "xy": "XY",
    "male": "XY",
    "m": "XY",
    "1": "XY",
}


def _normalize_sex(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text not in SEX_ALIASES:
        raise ValueError("expected_sex must be XX, XY, female, or male")
    return SEX_ALIASES[text]


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
    build: str | None = None,
    sex_vcf: str | Path | None = None,
    expected_sex: str | None = None,
    thresholds: ReadinessThresholds | None = None,
) -> ReadinessTable:
    if (depth is None) == (bam is None):
        raise ValueError("provide exactly one of --depth or --bam")
    if (bed is None) == (gtf is None):
        raise ValueError("provide exactly one of --bed or --gtf")
    if bam is not None and bed is None:
        raise ValueError("--bam requires --bed (samtools depth needs target intervals)")
    thresholds = thresholds or ReadinessThresholds()
    expected_sex = _normalize_sex(expected_sex)
    if expected_sex and sex_vcf is None:
        raise ValueError("expected_sex requires --sex-vcf")

    notes: list[str] = []
    if bed is not None:
        targets = load_bed_targets(bed)
        target_note = f"{len(targets)} BED targets"
        notes.append(f"{len(targets)} target(s) from BED")
    else:
        targets = load_gtf_targets(gtf, genes)
        target_note = f"{len(targets)} GTF exon targets"
        notes.append(f"{len(targets)} target(s) from GTF")

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
        depths, depth_stats = load_depth_for_targets(depth, targets)
        sources = [_source("depth", depth, "depth input")]
    sources[0].note = (
        (sources[0].note or "")
        + f"; {depth_stats.positions} positions"
        + (f"; {depth_stats.skipped} malformed lines skipped" if depth_stats.skipped else "")
        + (f"; {depth_stats.duplicates} duplicate positions" if depth_stats.duplicates else "")
        + (f"; {depth_stats.outside} positions outside targets skipped" if depth_stats.outside else "")
    ).strip("; ")
    sources.append(_source("targets", bed if bed is not None else gtf, target_note))

    caveat_regions = []
    if caveats is not None:
        caveat_regions = load_caveats(caveats)
        sources.append(_source("caveats", caveats, f"{len(caveat_regions)} caveat regions"))
        notes.append(f"caveats checked: {len(caveat_regions)} region(s)")
    else:
        notes.append("caveats not checked")

    if targets and not any(target.gene for target in targets):
        notes.append(
            "target BED has no gene names (BED3); gene-level summaries are "
            "unavailable; add a 4th-column gene symbol or use --gtf --genes"
        )

    target_chroms = {target.chrom for target in targets}
    depth_chroms = depth_stats.chroms
    if target_chroms and depth_chroms and target_chroms.isdisjoint(depth_chroms):
        notes.append(
            "no chromosome names shared between the targets and the depth input; "
            "check the build and contig naming"
        )
    if depth_stats.lines and not depths:
        notes.append(
            "depth has no positions inside the target intervals; check the "
            "BED/GTF coordinates"
        )
    if build:
        notes.append(f"build: {build}")

    rows = evaluate_targets(targets, depths, thresholds, caveat_regions)

    sample_qc = None
    if sex_vcf:
        signals = sex_signals(sex_vcf)
        concordance = None
        possible_swap = False
        if expected_sex and signals.inferred_sex in {"XX", "XY"}:
            concordance = signals.inferred_sex == expected_sex
            possible_swap = not concordance
        note = (
            f"sex check: inferred {signals.inferred_sex}"
            + (
                f" (X-het {signals.x_het_ratio:.3f}, {signals.x_sites} chrX sites, "
                f"{signals.y_variant_count} chrY sites)"
                if signals.x_het_ratio is not None
                else f" ({signals.x_sites} chrX sites, {signals.y_variant_count} chrY sites)"
            )
            + (f"; expected {expected_sex}" if expected_sex else "; expected sex not supplied")
        )
        if signals.inferred_sex not in {"XX", "XY"}:
            note += "; sex check inconclusive (no swap call)"
        if possible_swap:
            note += "; possible sample swap"
        sample_qc = SampleQC(
            inferred_sex=signals.inferred_sex,
            x_het_ratio=signals.x_het_ratio,
            x_sites=signals.x_sites,
            y_variant_count=signals.y_variant_count,
            expected_sex=expected_sex,
            sex_concordance=concordance,
            possible_swap=possible_swap,
            note=note,
        )
        sources.append(_source("sex_vcf", sex_vcf, "VCF sex-check input"))
        notes.append(note)
        if possible_swap:
            caveat = (
                f"possible sample swap: inferred {signals.inferred_sex} "
                f"vs expected {expected_sex}"
            )
            for row in rows:
                if caveat not in row.caveats:
                    row.caveats.append(caveat)
                if row.readiness == "ready":
                    row.readiness = "caution"
                    row.reason = caveat

    genes = summarize_by_gene(rows)
    meta = ReadinessMeta(
        sources=sources,
        thresholds=thresholds,
        build=build,
        caveats_checked=caveats is not None,
        caveat_regions=len(caveat_regions),
        sample_qc=sample_qc,
        contig_version=_contig_version(),
        notes=notes,
    )
    return ReadinessTable(rows=rows, meta=meta, genes=genes)


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


GENE_COLUMNS = [
    "gene", "targets", "bases", "covered_bases", "mean_depth",
    "pct_20x", "pct_50x", "pct_100x", "zero_bases", "caveats",
    "readiness", "reason",
]


def render_gene_tsv(table: ReadinessTable) -> str:
    lines = ["\t".join(GENE_COLUMNS)]
    for gene in table.genes:
        lines.append("\t".join(str(value) for value in [
            gene.gene, gene.targets, gene.bases, gene.covered_bases,
            f"{gene.mean_depth:.2f}", _pct(gene.pct_20x), _pct(gene.pct_50x),
            _pct(gene.pct_100x), gene.zero_bases, "; ".join(gene.caveats),
            gene.readiness, gene.reason,
        ]))
    return "\n".join(lines) + "\n"


def render_json(table: ReadinessTable) -> str:
    payload = {
        "meta": table.meta.model_dump(mode="json"),
        "targets": [asdict(row) for row in table.rows],
        "genes": [asdict(gene) for gene in table.genes],
    }
    return json.dumps(payload, indent=2) + "\n"


def write_table(
    table: ReadinessTable,
    path: str | Path,
    *,
    as_json: bool = False,
    by_gene: bool = False,
) -> None:
    if as_json:
        text = render_json(table)
    elif by_gene:
        text = render_gene_tsv(table)
    else:
        text = render_tsv(table)
    Path(path).write_text(text, encoding="utf-8")


def summarize(rows: list[TargetMetrics]) -> dict[str, int]:
    counts = {"ready": 0, "caution": 0, "not-interpretable": 0}
    for row in rows:
        counts[row.readiness] = counts.get(row.readiness, 0) + 1
    return counts
