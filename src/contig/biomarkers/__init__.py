"""Research-use oncology biomarker verification (M7).

TMB is computed from a somatic VCF + callable BED; MSI/LOH/CNV are recorded as
not_verified in v1. No treatment recommendations.
"""

from contig.biomarkers.models import BiomarkerEntry, BiomarkerMeta, BiomarkerReport

__all__ = ["BiomarkerEntry", "BiomarkerMeta", "BiomarkerReport"]
