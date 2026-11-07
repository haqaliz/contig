"""Research report builder (M4).

Builds a self-contained HTML research report from a run bundle plus optional
M1/M2 tables, and a machine-readable sidecar for staleness checks. No clinical
claims.
"""

from contig.reporting.models import ReportInput, ReportMeta, ReportSpec, Reviewer

__all__ = ["ReportInput", "ReportMeta", "ReportSpec", "Reviewer"]
