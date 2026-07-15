"""RNA-seq biological-plausibility evaluator (PRD C3, RNA-seq slice, Phase 2).

Turns a parsed per-sample MultiQC metrics dict into plausibility QCResults,
emitting explicit ``unverified`` for any plausibility metric a sample lacks.

The shared ``evaluate()`` SILENTLY SKIPS metrics absent from the dict; that is
exactly why the honest ``unverified`` branch lives here (in the wrapper), not
inside the shared evaluator.  Mirrors the germline pattern in variant_metrics.py
(evaluate_variant_plausibility).

A second honesty branch lives here too: a rule carrying ``"unit": "fraction"``
(currently only ``duplication_rate``, see rule_pack.py) declares its value must
sit in [0, 1]. A value PRESENT but outside that range signals a pre-scaled or
otherwise wrong-unit source (e.g. a 0-100 value where a 0-1 fraction was
expected) — this guard refuses it as ``unverified`` rather than rescaling,
because a value like 0.5 is ambiguous between "50%" and "0.5%" and guessing
would be worse than refusing.

Pure function of the ingested metrics: no tool execution, no network, no
randomness.  The path parse (parse_multiqc_general_stats_file) happens once at
the call site (Phase 3); this module takes the already-parsed dict.
"""

from __future__ import annotations

from contig.models import QCResult
from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK, evaluate

# The two plausibility checks this evaluator covers, in iteration order.
_CHECKS = ("duplication_rate", "rrna_contamination")


def _violates_unit_range(rule: dict, value: float) -> bool:
    """True if `rule` declares a "fraction" unit and `value` sits outside [0, 1].

    Rules with no "unit" key (e.g. rrna_contamination) are never guarded here.
    """
    return rule.get("unit") == "fraction" and not (0.0 <= value <= 1.0)


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
        which carries no severity and can never read as a pass. A metric
        present but violating its rule's declared ``"unit"`` range (see
        ``_violates_unit_range``) gets the same treatment, for the same
        reason: it carries no severity and is never rescaled into range.
    """
    rules = [_rule_by_check(n) for n in _CHECKS]
    results: list[QCResult] = []

    for sample, sample_metrics in metrics.items():
        # Build a sub-dict of only the present, in-unit-range metrics so
        # evaluate() can score them. Absent metrics and unit-range violations
        # are both handled below as unverified.
        computable = {
            r["metric"]: sample_metrics[r["metric"]]
            for r in rules
            if r["metric"] in sample_metrics
            and not _violates_unit_range(r, sample_metrics[r["metric"]])
        }
        results.extend(evaluate({sample: computable}, rules))

        for r in rules:
            metric = r["metric"]
            if metric not in sample_metrics:
                # Absent from this sample's report — never silently omit it.
                results.append(
                    QCResult(
                        check=f"{r['check']}:{sample}",
                        status="unverified",
                        message=f"{sample}: {metric} not reported by MultiQC",
                        value=None,
                        kind="metric",
                    )
                )
            elif _violates_unit_range(r, sample_metrics[metric]):
                # Present but outside its declared unit's range — refuse
                # rather than guess a rescaling.
                value = sample_metrics[metric]
                results.append(
                    QCResult(
                        check=f"{r['check']}:{sample}",
                        status="unverified",
                        message=(
                            f"{sample}: {metric}={value} violates its declared "
                            f"unit's [0, 1] fraction range — refusing rather "
                            f"than rescaling"
                        ),
                        value=None,
                        kind="metric",
                    )
                )

    return results
