"""Renderer tests for the annotation-cache-inputs / provenance-render aspect (M5a/M5b/N1).

The run record's parameters carry the input end of the annotation-cache chain
(`vep_cache`/`snpeff_cache` when user-supplied, `download_cache`/`outdir_cache`
when auto-downloaded); the renderers surface it so the chain "which cache was
configured -> which build was observed" is readable in `contig methods`, the
HTML report, and `contig show`. Records without cache inputs must render exactly
as today (no orphan label).
"""

from __future__ import annotations

from contig.methods import render_methods
from contig.models import (
    AnnotationProvenance,
    ExecutionTarget,
    QCResult,
    RunRecord,
    TaskEvent,
)
from contig.report import render_run_report, render_run_report_html


def _record(**overrides) -> RunRecord:
    """A sarek variant-calling record with both annotators (the realistic shape
    that carries cache inputs)."""
    base = dict(
        run_id="run-cache",
        pipeline="nf-core/sarek",
        pipeline_revision="3.5.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        parameters={},
        events=[TaskEvent(process="VEP", status="COMPLETED", exit=0)],
        qc_results=[QCResult(check="annotation_present", status="pass", message="ok", value=1.0)],
        annotation_identity=[
            AnnotationProvenance(tool="VEP", version="v110"),
            AnnotationProvenance(tool="SnpEff", version="5.1"),
        ],
    )
    base.update(overrides)
    return RunRecord(**base)


# ---------------------------------------------------------------------------
# Task 1 — methods line (M5a): the annotation clause gains a cache-input
# parenthetical when record.parameters carries cache inputs.
# ---------------------------------------------------------------------------


def test_methods_renders_user_supplied_cache_inputs():
    record = _record(parameters={"vep_cache": "/v", "snpeff_cache": "/s"})
    text = render_methods(record)
    assert "cache inputs VEP=/v, SnpEff=/s" in text


def test_methods_renders_single_user_supplied_cache_input_per_tool():
    # Only VEP's cache was supplied: the parenthetical names that tool's path
    # alone, never a fabricated SnpEff segment.
    record = _record(parameters={"vep_cache": "/v"})
    text = render_methods(record)
    assert "cache inputs VEP=/v" in text
    assert "SnpEff=" not in text


def test_methods_renders_auto_download_cache_input():
    # download_cache == "true" (the auto-download wiring) renders the download
    # wording; the outdir path itself stays out of the methods paragraph.
    record = _record(parameters={"download_cache": "true", "outdir_cache": "/c"})
    text = render_methods(record)
    assert "cache download" in text
    # the runs-dir path stays out of the parenthetical (it is noise in a methods
    # paragraph; the raw key/value still shows in the key-parameters clause)
    assert "cache download /c" not in text


def test_methods_ignores_download_cache_false():
    # Only "true" triggers the auto-download wording; a user's explicit "false"
    # is not a cache input (their caches are the vep_cache/snpeff_cache keys).
    record = _record(parameters={"download_cache": "false", "outdir_cache": "/c"})
    text = render_methods(record)
    assert "cache download" not in text
    assert "cache inputs" not in text


def test_methods_omits_cache_inputs_when_parameters_clean():
    # No cache keys at all: no parenthetical, no orphan label (the db_version
    # omission rule) -- the record renders exactly as before this aspect.
    text = render_methods(_record())
    assert "cache inputs" not in text
    assert "cache download" not in text