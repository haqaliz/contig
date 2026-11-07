"""Tests for readiness contracts."""

import pytest
from pydantic import ValidationError

from contig.readiness.models import ReadinessThresholds, Target


def test_threshold_defaults():
    thresholds = ReadinessThresholds()
    assert thresholds.depth_threshold == 20
    assert thresholds.ready_fraction == 0.90
    assert thresholds.caution_fraction == 0.50


def test_thresholds_reject_out_of_range_values():
    with pytest.raises(ValidationError):
        ReadinessThresholds(ready_fraction=1.5)
    with pytest.raises(ValidationError):
        ReadinessThresholds(depth_threshold=0)


def test_caution_fraction_cannot_exceed_ready_fraction():
    with pytest.raises(ValidationError):
        ReadinessThresholds(ready_fraction=0.5, caution_fraction=0.9)


def test_target_is_orderable_and_hashable():
    a = Target("1", 0, 10, "A")
    b = Target("1", 10, 20, "B")
    assert a < b
    assert {a, b}
