"""Tests for the methods-section generator (PRD contract C).

`render_methods` produces a deterministic, citation-ready methods paragraph from a
RunRecord: the pipeline plus revision, the assay, key params, container digests,
and the verdict plus QC summary. No LLM, no network; the same record renders the
same text every time.
"""

from contig.methods import render_methods
from contig.models import (
    ExecutionTarget,
    QCResult,
    RunRecord,
    TaskEvent,
)


def _record(**overrides) -> RunRecord:
    base = dict(
        run_id="run-1",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={"samplesheet.csv": "a" * 64},
        parameters={"genome": "GRCh38"},
        container_digests={"star": "sha256:deadbeef"},
        nextflow_version="24.10.0",
        events=[TaskEvent(process="STAR", status="COMPLETED", exit=0)],
        qc_results=[QCResult(check="mapping_rate", status="pass", message="ok", value=92.0)],
    )
    base.update(overrides)
    return RunRecord(**base)


def test_methods_names_the_pipeline_and_revision():
    text = render_methods(_record())
    assert "nf-core/rnaseq" in text
    assert "3.26.0" in text


def test_methods_names_the_assay():
    text = render_methods(_record())
    assert "RNA" in text or "rnaseq" in text


def test_methods_states_the_verdict():
    text = render_methods(_record())
    assert "pass" in text.lower()


def test_methods_mentions_key_params():
    text = render_methods(_record())
    assert "GRCh38" in text


def test_methods_mentions_container_digests():
    text = render_methods(_record())
    assert "sha256:deadbeef" in text


def test_methods_mentions_the_nextflow_version():
    text = render_methods(_record())
    assert "24.10.0" in text


def test_methods_summarizes_qc_checks():
    text = render_methods(_record())
    assert "mapping_rate" in text


def test_methods_is_deterministic():
    record = _record()
    assert render_methods(record) == render_methods(record)


def test_methods_is_a_nonempty_paragraph():
    text = render_methods(_record())
    assert len(text.strip()) > 0
    assert text.endswith(".")


def test_methods_handles_an_unverified_run():
    text = render_methods(_record(qc_results=[]))
    assert "unverified" in text.lower()


def test_methods_handles_a_pipeline_without_a_known_assay():
    text = render_methods(_record(pipeline="nf-core/unknown"))
    assert "nf-core/unknown" in text


def test_methods_contains_no_em_dash():
    text = render_methods(_record())
    assert "—" not in text
    assert "–" not in text
