"""Tests for cohort contracts."""

from contig.cohort.models import Cohort, CohortMeta, CohortVariant


def test_cohort_round_trip():
    cohort = Cohort(
        meta=CohortMeta(name="Lab", total_runs=2),
        variants=[CohortVariant(chrom="1", pos=10, ref="A", alt="G", seen_runs=1, frequency=0.5)],
    )
    again = Cohort.model_validate_json(cohort.model_dump_json())
    assert again.meta.name == "Lab"
    assert again.variants[0].frequency == 0.5
