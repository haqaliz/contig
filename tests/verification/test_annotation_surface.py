"""corroborated_by_line: read M4's concordance QCResults into a legible line (C7 M5).

The helper is PURE: it reads the already-computed `consequence_concordance` /
`gene_symbol_concordance` results (kind "concordance") plus `annotation_identity`,
and NEVER recomputes concordance. These tests build the QCResults with the exact
message strings `annotation_concordance.py` emits so the regex extraction is
pinned to the real format (PRD D2/D3, S-1).
"""

from __future__ import annotations

from contig.models import (
    AnnotationProvenance,
    ExecutionTarget,
    QCResult,
    RunRecord,
)
from contig.verification.annotation_surface import corroborated_by_line


def _record(qc_results, annotation_identity):
    return RunRecord(
        run_id="run-m5",
        pipeline="nf-core/sarek",
        pipeline_revision="3.5.1",
        target=ExecutionTarget(
            backend="local", container_runtime="docker", work_dir="/tmp/run"
        ),
        input_checksums={},
        qc_results=qc_results,
        annotation_identity=annotation_identity,
    )


def _consequence_pass():
    # Exact message format from evaluate_consequence_concordance (pass branch).
    return QCResult(
        check="consequence_concordance",
        status="pass",
        message=(
            "vep vs snpeff: 47/50 shared site(s) agree on the most-severe "
            "consequence (agreement 0.94); layout=two-file"
        ),
        value=0.94,
        expected_range=">= 0.9",
        kind="concordance",
    )


def _gene_symbol_pass():
    # Exact message format from evaluate_gene_symbol_concordance (pass branch).
    return QCResult(
        check="gene_symbol_concordance",
        status="pass",
        message=(
            "vep vs snpeff: 45/50 resolvable gene-symbol pair(s) agree "
            "(agreement 0.9); informational only, never affects the verdict"
        ),
        value=0.9,
        expected_range=None,
        kind="concordance",
    )


def _both_annotators():
    return [
        AnnotationProvenance(tool="VEP", version="v110", db_version="110_GRCh38"),
        AnnotationProvenance(tool="SnpEff", version="5.1d", db_version="GRCh38.105"),
    ]


def test_dual_annotated_full_line():
    # Both concordance results present with values -> full line naming both
    # annotators + both fractions + the informational mark (D3/S-1).
    record = _record(
        [_consequence_pass(), _gene_symbol_pass()], _both_annotators()
    )
    line = corroborated_by_line(record)
    assert line == (
        "Corroborated by VEP and SnpEff: 47/50 consequences agree (0.94); "
        "gene symbols 45/50 (0.90, informational)."
    )


def test_consequence_only_half_line():
    # gene_symbol_concordance absent -> render only the consequence half, no
    # gene-symbol clause.
    record = _record([_consequence_pass()], _both_annotators())
    line = corroborated_by_line(record)
    assert line == (
        "Corroborated by VEP and SnpEff: 47/50 consequences agree (0.94)."
    )
    assert "gene symbols" not in line


def test_consequence_value_none_returns_none():
    # Below-floor UNVERIFIED consequence check (value None) -> return None (D2).
    unverified = QCResult(
        check="consequence_concordance",
        status="unverified",
        message=(
            "vep and snpeff share 3 variant site(s) (< 10 needed); too few to "
            "corroborate (concordance is not ground truth)"
        ),
        value=None,
        expected_range=">= 0.9",
        kind="concordance",
    )
    record = _record([unverified, _gene_symbol_pass()], _both_annotators())
    assert corroborated_by_line(record) is None


def test_single_annotator_returns_none():
    # Only one annotator ran: both concordance checks are UNVERIFIED with value
    # None -> return None (no fabricated agreement, D2/G2).
    message = (
        "only VEP annotation is present under this run; the other annotator did "
        "not run (e.g. a missing SnpEff cache) -- cannot compute concordance"
    )
    cons = QCResult(
        check="consequence_concordance",
        status="unverified",
        message=message,
        value=None,
        expected_range=">= 0.9",
        kind="concordance",
    )
    gs = QCResult(
        check="gene_symbol_concordance",
        status="unverified",
        message=message,
        value=None,
        expected_range=None,
        kind="concordance",
    )
    record = _record(
        [cons, gs],
        [AnnotationProvenance(tool="VEP", version="v110")],
    )
    assert corroborated_by_line(record) is None
