"""RNA-seq biological-plausibility evaluator (PRD C3, RNA-seq slice, Phase 2).

Turns a parsed per-sample MultiQC metrics dict into plausibility QCResults,
emitting explicit ``unverified`` for any plausibility metric a sample lacks.

The shared ``evaluate()`` SILENTLY SKIPS metrics absent from the dict; that is
exactly why the honest ``unverified`` branch lives here (in the wrapper), not
inside the shared evaluator.  Mirrors the germline pattern in variant_metrics.py
(evaluate_variant_plausibility).

Pure function of the ingested metrics: no tool execution, no network, no
randomness.  The path parse (parse_multiqc_general_stats_file) happens once at
the call site (Phase 3); this module takes the already-parsed dict.
"""

from __future__ import annotations

from contig.models import QCResult
from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK, evaluate

# The two plausibility checks this evaluator covers, in iteration order.
_CHECKS = ("duplication_rate", "rrna_contamination")


def _rule_by_check(name: str) -> dict:
    """Look up one rule in RNASEQ_PLAUSIBILITY_PACK by its check name."""
    for rule in RNASEQ_PLAUSIBILITY_PACK:
        if rule["check"] == name:
            return rule
    raise KeyError(name)


def evaluate_rnaseq_plausibility(
    metrics: dict[str, dict[str, float]],
) -> list[QCResult]:
    """Evaluate RNA-seq plausibility rules over a per-sample metrics dict.

    Parameters
    ----------
    metrics:
        ``{sample: {metric_slug: value}}`` — the same shape that
        ``qc_ingest.parse_multiqc_general_stats_file`` returns.

    Returns
    -------
    list[QCResult]
        One result per (sample, plausibility check) pair.  Computable metrics
        go through the shared ``evaluate()`` so band logic and check naming
        (``"<check>:<sample>"``) stay single-sourced in ``rule_pack.py``.
        A metric absent from a sample's dict gets an explicit
        ``status="unverified"`` result (``value=None``, ``kind="metric"``),
        which carries no severity and can never read as a pass.
    """
    rules = [_rule_by_check(n) for n in _CHECKS]
    results: list[QCResult] = []

    for sample, sample_metrics in metrics.items():
        # Build a sub-dict of only the metrics that are present so evaluate()
        # can score them.  Absent metrics are handled below as unverified.
        computable = {
            r["metric"]: sample_metrics[r["metric"]]
            for r in rules
            if r["metric"] in sample_metrics
        }
        results.extend(evaluate({sample: computable}, rules))

        # For every plausibility metric absent from this sample's report,
        # emit an explicit unverified result — never silently omit it.
        for r in rules:
            if r["metric"] not in sample_metrics:
                results.append(
                    QCResult(
                        check=f"{r['check']}:{sample}",
                        status="unverified",
                        message=f"{sample}: {r['metric']} not reported by MultiQC",
                        value=None,
                        kind="metric",
                    )
                )

    return results
