"""Deterministic coverage metrics and readiness states."""

from __future__ import annotations

from contig.readiness.caveats import overlapping_caveats
from contig.readiness.models import (
    CaveatRegion,
    GeneMetrics,
    ReadinessThresholds,
    Target,
    TargetMetrics,
)


def evaluate_target(
    target: Target,
    depths: dict[tuple[str, int], int],
    thresholds: ReadinessThresholds,
    caveats: list[CaveatRegion],
) -> TargetMetrics:
    bases = max(0, target.end - target.start)
    values = [depths.get((target.chrom, pos), 0) for pos in range(target.start + 1, target.end + 1)]
    if bases == 0:
        values = []

    covered = sum(1 for value in values if value > 0)
    mean_depth = (sum(values) / bases) if bases else 0.0
    pct_20x = (sum(1 for value in values if value >= 20) / bases) if bases else 0.0
    pct_50x = (sum(1 for value in values if value >= 50) / bases) if bases else 0.0
    pct_100x = (sum(1 for value in values if value >= 100) / bases) if bases else 0.0
    pct_at_threshold = (
        sum(1 for value in values if value >= thresholds.depth_threshold) / bases
        if bases else 0.0
    )

    overlap = overlapping_caveats(target, caveats)
    caveat_labels = [f"{region.name}: {region.reason}" for region in overlap]

    if bases == 0:
        readiness = "not-interpretable"
        reason = "empty target"
    elif pct_at_threshold < thresholds.caution_fraction:
        readiness = "not-interpretable"
        if covered == 0:
            reason = "0 covered bases"
        else:
            reason = (
                f"{pct_at_threshold:.1%} at {thresholds.depth_threshold}x is below "
                f"the caution floor {thresholds.caution_fraction:.0%}"
            )
    elif caveat_labels:
        readiness = "caution"
        reason = "caveat: " + "; ".join(caveat_labels)
    elif pct_at_threshold < thresholds.ready_fraction:
        readiness = "caution"
        reason = (
            f"{pct_at_threshold:.1%} at {thresholds.depth_threshold}x is below "
            f"the ready floor {thresholds.ready_fraction:.0%}"
        )
    elif mean_depth < thresholds.depth_threshold:
        readiness = "caution"
        reason = f"mean {mean_depth:.1f}x is below {thresholds.depth_threshold}x"
    else:
        readiness = "ready"
        reason = (
            f"mean {mean_depth:.1f}x; "
            f"{pct_at_threshold:.1%} at {thresholds.depth_threshold}x"
        )

    return TargetMetrics(
        target=target,
        bases=bases,
        covered_bases=covered,
        mean_depth=mean_depth,
        pct_20x=pct_20x,
        pct_50x=pct_50x,
        pct_100x=pct_100x,
        zero_bases=bases - covered,
        caveats=caveat_labels,
        readiness=readiness,
        reason=reason,
    )


def evaluate_targets(
    targets: list[Target],
    depths: dict[tuple[str, int], int],
    thresholds: ReadinessThresholds,
    caveats: list[CaveatRegion],
) -> list[TargetMetrics]:
    return [evaluate_target(target, depths, thresholds, caveats) for target in targets]


def summarize_by_gene(rows: list[TargetMetrics]) -> list[GeneMetrics]:
    grouped: dict[str, list[TargetMetrics]] = {}
    for row in rows:
        gene = row.target.gene
        if gene:
            grouped.setdefault(gene, []).append(row)
    summaries: list[GeneMetrics] = []
    rank = {"not-interpretable": 0, "caution": 1, "ready": 2}
    for gene, gene_rows in sorted(grouped.items()):
        bases = sum(row.bases for row in gene_rows)
        covered = sum(row.covered_bases for row in gene_rows)
        zero = sum(row.zero_bases for row in gene_rows)
        caveats = sorted({caveat for row in gene_rows for caveat in row.caveats})
        worst = min(gene_rows, key=lambda row: rank.get(row.readiness, 0))
        summaries.append(GeneMetrics(
            gene=gene,
            targets=len(gene_rows),
            bases=bases,
            covered_bases=covered,
            mean_depth=(
                sum(row.mean_depth * row.bases for row in gene_rows) / bases if bases else 0.0
            ),
            pct_20x=(
                sum(row.pct_20x * row.bases for row in gene_rows) / bases if bases else 0.0
            ),
            pct_50x=(
                sum(row.pct_50x * row.bases for row in gene_rows) / bases if bases else 0.0
            ),
            pct_100x=(
                sum(row.pct_100x * row.bases for row in gene_rows) / bases if bases else 0.0
            ),
            zero_bases=zero,
            caveats=caveats,
            readiness=worst.readiness,
            reason=f"{len(gene_rows)} target(s); worst {worst.readiness}: {worst.reason}",
        ))
    return summaries
