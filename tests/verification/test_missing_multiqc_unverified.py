"""C3-12: a missing MultiQC report must surface as UNVERIFIED, never vanish.

Before this, `_discover_qc`'s `multiqc is not None` gate skipped every metric
check silently when no report was found. A run whose structural checks passed
then rendered as PASS with zero metric coverage -- the false-pass shape the
guardrails forbid. The metric checks still do not run (there is nothing to run
them over); the point is that the gap is now *recorded* as UNVERIFIED.
"""

from __future__ import annotations

from pathlib import Path

from contig.runner import _discover_qc


def test_missing_multiqc_emits_one_unverified_check(tmp_path: Path) -> None:
    results = _discover_qc(tmp_path, "rnaseq")
    missing = [r for r in results if r.check == "multiqc_report"]
    assert len(missing) == 1
    assert missing[0].status == "unverified"
    # Observable, not an assertion: it must not claim a pass or carry severity.
    assert missing[0].informational is False
    assert missing[0].value is None


def test_present_multiqc_emits_no_missing_report_check(tmp_path: Path) -> None:
    report = tmp_path / "multiqc" / "multiqc_data.json"
    report.parent.mkdir(parents=True)
    report.write_text('{"report_general_stats_data": [{"S1": {"x": 1}}]}')
    results = _discover_qc(tmp_path, "rnaseq")
    assert [r for r in results if r.check == "multiqc_report"] == []


def test_dedicated_metric_assay_gets_no_generic_report_check(tmp_path: Path) -> None:
    # methylseq owns its own artifact gate and deliberately stays out of the
    # generic MultiQC pack; a generic "report missing" line would be noise.
    results = _discover_qc(tmp_path, "methylseq")
    assert [r for r in results if r.check == "multiqc_report"] == []
