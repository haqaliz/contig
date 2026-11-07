"""Local cohort frequency layer (M8 v1).

Aggregates M1 variant tables on this machine only. No network, no federated
sharing, no sample identifiers.
"""

from contig.cohort.models import Cohort, CohortMeta, CohortRun, CohortVariant, GeneSummary

__all__ = ["Cohort", "CohortMeta", "CohortRun", "CohortVariant", "GeneSummary"]
