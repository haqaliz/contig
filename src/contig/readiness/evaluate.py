"""Deterministic coverage metrics and readiness states."""

from __future__ import annotations

from contig.readiness.caveats import overlapping_caveats
from contig.readiness.models import (
    CaveatRegion,
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
