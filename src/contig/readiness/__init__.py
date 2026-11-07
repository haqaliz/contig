"""Coverage and interpretation-readiness workbench (M2).

A data-sufficiency check over a target panel: per-target depth metrics and a
deterministic ready/caution/not-interpretable state. No clinical claim.
"""

from contig.readiness.models import (
    CaveatRegion,
    ReadinessMeta,
    ReadinessTable,
    ReadinessThresholds,
    SourceProvenance,
    Target,
    TargetMetrics,
)

__all__ = [
    "CaveatRegion",
    "ReadinessMeta",
    "ReadinessTable",
    "ReadinessThresholds",
    "SourceProvenance",
    "Target",
    "TargetMetrics",
]
