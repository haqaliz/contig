"""Tests for report summaries."""

import json
from pathlib import Path

from contig.reporting.inputs import load_run_bundle
from contig.reporting.summaries import (
    qc_summary,
    readiness_summary,
    variant_summary,
    verdict_label,
)

FIX = Path(__file__).parent / "fixtures" / "reporting"


def test_variant_summary_buckets_and_genes():
    payload = json.loads((FIX / "variants.json").read_text())
    summary = variant_summary(payload)
    assert summary["total"] == 3
    assert summary["clinvar"]["pathogenic"] == 1
    assert summary["clinvar"]["likely_pathogenic"] == 1
    assert summary["clinvar"]["absent"] == 1
    assert summary["top_genes"][0] == ("BRCA1", 1)


def test_readiness_summary_counts_and_blocked_targets():
    payload = json.loads((FIX / "readiness.json").read_text())
    summary = readiness_summary(payload)
    assert summary["total"] == 3
    assert summary["counts"] == {"ready": 1, "caution": 1, "not-interpretable": 1}
    assert summary["blocked"] == ["GENE3"]


def test_qc_summary_counts_and_deciding_checks():
    record = load_run_bundle(FIX / "runs", "r1")
    summary = qc_summary(record)
    assert summary["counts"] == {"pass": 1, "warn": 1, "fail": 0, "unverified": 0}
    assert summary["deciding"] == ["library_size_skew"]
    assert summary["verdict"] == "warn"


def test_verdict_labels_are_honest():
    assert verdict_label("pass").startswith("PASS")
    assert verdict_label("warn").startswith("WARN")
    assert verdict_label("fail").startswith("FAIL")
    assert verdict_label("unverified").startswith("UNVERIFIED")
