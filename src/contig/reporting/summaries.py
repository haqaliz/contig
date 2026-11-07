"""Plain summaries used by the report renderer."""

from __future__ import annotations

from collections import Counter
from typing import Any

from contig.models import RunRecord
from contig.variants.filters import clinvar_rank

CLINVAR_BUCKETS = [
    (0, "pathogenic"),
    (1, "likely_pathogenic"),
    (2, "conflicting"),
    (3, "uncertain"),
    (4, "likely_benign"),
    (5, "benign"),
    (6, "not_reported"),
    (7, "absent"),
]


def variant_summary(payload: dict[str, Any]) -> dict[str, Any]:
    variants = payload.get("variants", [])
    buckets = {name: 0 for _, name in CLINVAR_BUCKETS}
    genes: Counter[str] = Counter()
    for row in variants:
        rank = clinvar_rank(row.get("clinvar_significance"))
        buckets[dict(CLINVAR_BUCKETS).get(rank, "not_reported")] += 1
        gene = row.get("gene")
        if gene:
            genes[gene] += 1
    meta = payload.get("meta", {})
    return {
        "total": len(variants),
        "clinvar": buckets,
        "top_genes": genes.most_common(10),
        "filters": meta.get("filters", {}),
        "source_count": len(meta.get("sources", [])),
    }


def readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    targets = payload.get("targets", [])
    counts = {"ready": 0, "caution": 0, "not-interpretable": 0}
    blocked: list[str] = []
    for row in targets:
        state = row.get("readiness", "not-interpretable")
        counts[state] = counts.get(state, 0) + 1
        if state == "not-interpretable":
            blocked.append(row.get("target", {}).get("name", "unknown"))
    meta = payload.get("meta", {})
    return {
        "total": len(targets),
        "counts": counts,
        "blocked": blocked[:20],
        "thresholds": meta.get("thresholds", {}),
    }


def qc_summary(record: RunRecord) -> dict[str, Any]:
    counts = {"pass": 0, "warn": 0, "fail": 0, "unverified": 0}
    deciding: list[str] = []
    for result in record.qc_results:
        counts[result.status] = counts.get(result.status, 0) + 1
        if result.status in {"fail", "warn"}:
            deciding.append(result.check)
    return {
        "counts": counts,
        "deciding": deciding,
        "verdict": record.verdict,
    }


def verdict_label(verdict: str) -> str:
    return {
        "pass": "PASS — ran and verified",
        "warn": "WARN — completed with caveats",
        "fail": "FAIL — do not trust the output",
        "unverified": "UNVERIFIED — nothing checked it",
    }.get(verdict, verdict.upper())
