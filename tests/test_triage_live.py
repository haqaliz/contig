"""Manual live gate for the real Jev triage transport (PRD S2, BYOK).

This test is the owner's smoke check against a real `CONTIG_JEV_URL` with a
real `CONTIG_JEV_KEY` — it is unconditionally skipped so it never runs in CI
and never fires incidentally in a full local suite. To run it, remove the
skip marker locally and set CONTIG_JEV_KEY + CONTIG_JEV_URL (https, or
http://localhost with CONTIG_JEV_ALLOW_HTTP set).

The assertion is shape-only: the seam must return a well-formed
`TriageResult` and must never raise, whatever the vendor reply is.
"""

import pytest

from contig.triage import TriageResult, default_jev_triage


@pytest.mark.skip(
    reason="manual live gate (S2): owner-run with a real CONTIG_JEV_KEY/"
    "CONTIG_JEV_URL; never run in CI"
)
def test_real_jev_triage_round_trip_shape() -> None:
    request = _live_request()

    result = default_jev_triage(request)

    assert isinstance(result, TriageResult)
    assert isinstance(result.mode, str) and result.mode
    if result.confidence is not None:
        assert 0.0 <= result.confidence <= 1.0
    for item_id, confidence in result.items.items():
        assert item_id.startswith(f"{request.run_id}:{request.surface}:")
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0
    if result.mode == "null":
        assert result.reason is not None
    else:
        assert result.reason is None


def _live_request():
    from contig.triage import TriageRequest, build_triage_payload

    return TriageRequest(
        run_id="manual-live-gate",
        surface="qc_anomaly",
        mode="shadow",
        payload=build_triage_payload(
            {
                "run_id": "manual-live-gate",
                "assay": "rna-seq",
                "pipeline": "nf-core/rnaseq",
                "task_counts": 1,
                "failed_tasks": 0,
                "repair_attempts": 0,
                "verdict": "PASS",
                "files": [
                    {"path": "/reads/x.fastq.gz", "size": 1, "sha256": "a" * 64}
                ],
            },
            [
                {
                    "check": "insert_size_median",
                    "kind": "metric",
                    "status": "PASS",
                    "value": 331.0,
                    "expected_range": {"min": 250, "max": 500},
                }
            ],
        ),
    )