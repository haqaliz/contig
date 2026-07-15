import pytest
from pydantic import ValidationError

from contig.models import (
    ExecutionTarget,
    QCResult,
    RunRecord,
    RunSummary,
    TaskEvent,
    overall_verdict,
    sha256_file,
)


def _qc(status):
    return QCResult(check="alignment_rate", status=status, message="x")


def test_execution_target_defaults_engine_to_nextflow():
    target = ExecutionTarget(backend="local", container_runtime="docker", work_dir="/tmp/run")
    assert target.engine == "nextflow"


def test_execution_target_rejects_unknown_backend():
    with pytest.raises(ValidationError):
        ExecutionTarget(backend="mainframe", container_runtime="docker", work_dir="/tmp/run")


def test_overall_verdict_fail_dominates_warn_and_pass():
    assert overall_verdict([_qc("pass"), _qc("warn"), _qc("fail")]) == "fail"


def test_overall_verdict_warn_when_no_fail_present():
    assert overall_verdict([_qc("pass"), _qc("warn"), _qc("pass")]) == "warn"


def test_overall_verdict_pass_when_all_pass():
    assert overall_verdict([_qc("pass"), _qc("pass")]) == "pass"


def test_overall_verdict_rejects_empty_list_to_prevent_false_pass():
    with pytest.raises(ValueError):
        overall_verdict([])


def test_overall_verdict_all_informational_reduces_to_unverified():
    informational_pass = QCResult(check="c", status="pass", message="m", informational=True)
    assert overall_verdict([informational_pass]) == "unverified"


def test_overall_verdict_informational_pass_plus_asserting_pass_is_pass():
    informational_pass = QCResult(check="c", status="pass", message="m", informational=True)
    assert overall_verdict([informational_pass, _qc("pass")]) == "pass"


def test_overall_verdict_informational_pass_plus_unverified_is_unverified():
    informational_pass = QCResult(check="c", status="pass", message="m", informational=True)
    assert overall_verdict([informational_pass, _qc("unverified")]) == "unverified"


def test_overall_verdict_informational_pass_does_not_mask_fail_or_warn():
    informational_pass = QCResult(check="c", status="pass", message="m", informational=True)
    assert overall_verdict([informational_pass, _qc("fail")]) == "fail"
    assert overall_verdict([informational_pass, _qc("warn")]) == "warn"


def test_qc_result_defaults_kind_to_metric():
    assert QCResult(check="alignment_rate", status="pass", message="x").kind == "metric"


def test_qc_result_accepts_structural_kind():
    result = QCResult(check="output_present:a.bam", status="fail", message="x", kind="structural")
    assert result.kind == "structural"


def test_qc_result_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        QCResult(check="x", status="pass", message="x", kind="vibes")


def test_qc_result_defaults_informational_to_false():
    assert QCResult(check="c", status="pass", message="m").informational is False


def test_qc_result_legacy_dict_without_informational_key_defaults_false():
    # A pre-field record has no `informational` key at all; it must still
    # deserialize (never raise) and default to False, exactly like the
    # QCKind back-compat contract above.
    result = QCResult.model_validate({"check": "c", "status": "pass", "message": "m"})
    assert result.informational is False


def test_task_event_is_failure_on_failed_status():
    assert TaskEvent(process="STAR_ALIGN", status="FAILED").is_failure is True


def test_task_event_is_failure_on_nonzero_exit():
    assert TaskEvent(process="STAR_ALIGN", status="COMPLETED", exit=137).is_failure is True


def test_task_event_not_failure_when_completed_exit_zero():
    assert TaskEvent(process="STAR_ALIGN", status="COMPLETED", exit=0).is_failure is False


def test_run_summary_from_events_counts_and_flags_failure():
    events = [
        TaskEvent(process="FASTQC", status="COMPLETED", exit=0),
        TaskEvent(process="STAR_ALIGN", status="FAILED", exit=137),
    ]
    summary = RunSummary.from_events(events)
    assert summary.total_tasks == 2
    assert summary.failed_tasks == 1
    assert summary.succeeded is False


def test_run_summary_from_events_succeeds_when_all_pass():
    events = [TaskEvent(process="FASTQC", status="COMPLETED", exit=0)]
    assert RunSummary.from_events(events).succeeded is True


def test_sha256_file_matches_known_digest(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_bytes(b"hello")
    assert sha256_file(f) == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def _minimal_record(qc_results, events=None):
    return RunRecord(
        run_id="run-001",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.14.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="/tmp/run"),
        input_checksums={"reads_R1.fastq.gz": "abc123"},
        parameters={"aligner": "star_salmon"},
        qc_results=qc_results,
        events=events or [],
    )


_OK_TASK = TaskEvent(process="FASTQC", status="COMPLETED", exit=0)
_BAD_TASK = TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)


def test_run_record_verdict_is_fail_when_any_qc_fails():
    record = _minimal_record([_qc("pass"), _qc("fail")], events=[_OK_TASK])
    assert record.verdict == "fail"


def test_run_record_verdict_is_pass_when_run_ok_and_all_qc_pass():
    record = _minimal_record([_qc("pass"), _qc("pass")], events=[_OK_TASK])
    assert record.verdict == "pass"


def test_run_record_verdict_is_fail_when_a_task_failed_even_if_qc_passes():
    record = _minimal_record([_qc("pass")], events=[_OK_TASK, _BAD_TASK])
    assert record.verdict == "fail"


def test_run_record_verdict_is_unverified_when_run_ok_but_no_qc():
    record = _minimal_record([], events=[_OK_TASK])
    assert record.verdict == "unverified"


def test_run_record_verdict_is_warn_when_run_ok_and_qc_warns():
    record = _minimal_record([_qc("pass"), _qc("warn")], events=[_OK_TASK])
    assert record.verdict == "warn"


def test_run_record_serializes_verdict_into_json():
    # The dashboard reads run_record.json directly, so the trust verdict must be
    # in the serialized record, not only a computed Python property (no TS reimpl).
    import json

    record = _minimal_record([_qc("pass")], events=[_OK_TASK])
    data = json.loads(record.model_dump_json())
    assert data["verdict"] == "pass"


def test_annotation_identity_accepts_legacy_singular():
    # Pre-M4 bundles serialized `annotation_identity` as a SINGLE object (the
    # first-annotator-found shape). M4 stores a list (both VEP + SnpEff), so a
    # legacy bundle's dict must still deserialize -- as a one-element list --
    # rather than fail validation and lock old bundles out of verify/reproduce.
    from contig.models import AnnotationProvenance

    legacy_dict = {
        "run_id": "run-legacy",
        "pipeline": "nf-core/sarek",
        "pipeline_revision": "3.5.1",
        "target": {"backend": "local", "container_runtime": "docker", "work_dir": "/tmp/run"},
        "input_checksums": {},
        "annotation_identity": {"tool": "VEP", "version": "v110"},
    }
    record = RunRecord.model_validate(legacy_dict)
    assert record.annotation_identity == [AnnotationProvenance(tool="VEP", version="v110")]


def test_annotation_identity_legacy_dict_without_db_version_defaults_none():
    # Pre-M5 bundles serialized annotation entries with no `db_version` key. Such
    # a dict must still load and default `db_version` to None (never fabricated),
    # so old bundles verify/reproduce unchanged.
    from contig.models import AnnotationProvenance

    legacy_dict = {
        "run_id": "run-pre-m5",
        "pipeline": "nf-core/sarek",
        "pipeline_revision": "3.5.1",
        "target": {"backend": "local", "container_runtime": "docker", "work_dir": "/tmp/run"},
        "input_checksums": {},
        "annotation_identity": [{"tool": "VEP", "version": "v110"}],
    }
    record = RunRecord.model_validate(legacy_dict)
    assert record.annotation_identity == [AnnotationProvenance(tool="VEP", version="v110")]
    assert record.annotation_identity[0].db_version is None


def test_annotation_identity_defaults_to_empty_list():
    record = _minimal_record([])
    assert record.annotation_identity == []


def test_annotation_identity_none_normalizes_to_empty_list():
    record = RunRecord.model_validate(
        {
            "run_id": "run-none",
            "pipeline": "nf-core/rnaseq",
            "pipeline_revision": "3.14.0",
            "target": {"backend": "local", "container_runtime": "docker", "work_dir": "/tmp/run"},
            "input_checksums": {},
            "annotation_identity": None,
        }
    )
    assert record.annotation_identity == []


# --- SexInference (germline provenance capture) ---------------------------------


def test_sex_inference_defaults_to_none():
    record = _minimal_record([])
    assert record.sex_inference is None


def test_sex_inference_legacy_dict_without_key_loads_as_none():
    # A pre-slice bundle's JSON simply lacks the `sex_inference` key -- it must
    # still load (never raise) and default to None, exactly like the
    # ReferenceIdentity back-compat contract.
    legacy_dict = {
        "run_id": "run-pre-sex-inference",
        "pipeline": "nf-core/sarek",
        "pipeline_revision": "3.5.1",
        "target": {"backend": "local", "container_runtime": "docker", "work_dir": "/tmp/run"},
        "input_checksums": {},
    }
    record = RunRecord.model_validate(legacy_dict)
    assert record.sex_inference is None


def test_sex_inference_round_trips_when_set():
    from contig.models import SexInference

    record = _minimal_record([])
    record.sex_inference = SexInference(
        inferred_sex="XY",
        x_het_ratio=0.02,
        x_sites=143,
        y_variant_count=6,
        par_masked=True,
        reference_build="GRCh38",
    )
    reloaded = RunRecord.model_validate_json(record.model_dump_json())
    assert reloaded.sex_inference == record.sex_inference


def test_diagnosis_rejects_confidence_above_one():
    from contig.models import Diagnosis

    with pytest.raises(ValidationError):
        Diagnosis(failure_class="oom", root_cause="x", evidence=["e"], confidence=1.5)


def test_failureclass_includes_the_broader_nfcore_classes():
    # The taxonomy must carry the broader nf-core failure classes the detector
    # now names, so a Diagnosis round-trips through the model for each.
    from typing import get_args

    from contig.models import Diagnosis, FailureClass

    classes = set(get_args(FailureClass))
    for cls in ("disk_full", "download_failed", "permission_denied"):
        assert cls in classes
        d = Diagnosis(failure_class=cls, root_cause="x", confidence=0.9)
        assert Diagnosis.model_validate_json(d.model_dump_json()).failure_class == cls


def test_patch_rejects_unknown_kind():
    from contig.models import Patch

    with pytest.raises(ValidationError):
        Patch(kind="teleport", operation={}, rationale="x", risk="safe", expected_signal="y")


def test_repair_step_composes_diagnosis_and_patch():
    from contig.models import Diagnosis, Patch, RepairStep

    step = RepairStep(
        attempt=1,
        diagnosis=Diagnosis(failure_class="oom", root_cause="OOM", evidence=["exit 137"], confidence=0.9),
        patch=Patch(
            kind="resource",
            operation={"set": {"memory": "8.GB"}},
            rationale="bump memory",
            risk="safe",
            expected_signal="no OOM",
        ),
        outcome="patched_and_retried",
    )
    assert step.diagnosis.failure_class == "oom"
    assert step.patch.risk == "safe"


def test_pipeline_entry_holds_assay_pipeline_revision():
    from contig.models import PipelineEntry

    entry = PipelineEntry(assay="rnaseq", pipeline="nf-core/rnaseq", revision="3.26.0", description="RNA-seq DE")
    assert entry.assay == "rnaseq"
    assert entry.pipeline == "nf-core/rnaseq"
    assert entry.revision == "3.26.0"


def test_data_shape_rejects_unknown_layout():
    from contig.models import DataShape

    with pytest.raises(ValidationError):
        DataShape(n_samples=2, layout="quantum", warnings=[])


def test_data_shape_holds_sample_count_and_warnings():
    from contig.models import DataShape

    shape = DataShape(n_samples=1, layout="single", warnings=["only 1 sample; needs replicates"])
    assert shape.n_samples == 1
    assert shape.layout == "single"
    assert "replicates" in shape.warnings[0]


def test_plan_composes_pipeline_params_and_warnings():
    from contig.models import Plan

    plan = Plan(
        assay="rnaseq",
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        params={"input": "samplesheet.csv", "genome": "GRCh38"},
        rationale="goal 'find DE genes' → rnaseq",
        warnings=["single-end reads detected"],
    )
    assert plan.pipeline == "nf-core/rnaseq"
    assert plan.params["genome"] == "GRCh38"
    assert plan.warnings == ["single-end reads detected"]


def test_launch_manifest_derives_is_test_profile_from_missing_input():
    from contig.models import LaunchManifest

    manifest = LaunchManifest(
        run_id="run-1",
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        profiles=["test", "docker"],
        backend="local",
        container_runtime="docker",
        input=None,
        max_attempts=3,
        created_at="2026-06-22T00:00:00+00:00",
    )
    assert manifest.is_test_profile is True


def test_launch_manifest_is_not_test_profile_when_input_present():
    from contig.models import LaunchManifest

    manifest = LaunchManifest(
        run_id="run-1",
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        profiles=["docker"],
        backend="local",
        container_runtime="docker",
        input="/abs/sheet.csv",
        genome="GRCh38",
        max_attempts=3,
        created_at="2026-06-22T00:00:00+00:00",
    )
    assert manifest.is_test_profile is False


def test_launch_manifest_serializes_is_test_profile_into_json():
    import json

    from contig.models import LaunchManifest

    manifest = LaunchManifest(
        run_id="run-1",
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        profiles=["test", "docker"],
        backend="local",
        container_runtime="docker",
        input=None,
        max_attempts=3,
        created_at="2026-06-22T00:00:00+00:00",
    )
    data = json.loads(manifest.model_dump_json())
    assert data["is_test_profile"] is True
    assert data["input"] is None
    assert "outdir" not in data and "work_dir" not in data


def test_reference_identity_round_trips_via_json():
    from contig.models import ReferenceIdentity

    identity = ReferenceIdentity(
        mode="explicit",
        fasta="ref.fa",
        gtf="genes.gtf",
        fasta_sha256="a" * 64,
        gtf_sha256="b" * 64,
    )
    restored = ReferenceIdentity.model_validate_json(identity.model_dump_json())
    assert restored.mode == "explicit"
    assert restored.fasta == "ref.fa"
    assert restored.gtf == "genes.gtf"
    assert restored.fasta_sha256 == "a" * 64
    assert restored.gtf_sha256 == "b" * 64


def test_run_record_reference_identity_defaults_to_none():
    record = _minimal_record([_qc("pass")], events=[_OK_TASK])
    assert record.reference_identity is None


def test_run_record_with_reference_identity_round_trips_via_json():
    from contig.models import ReferenceIdentity

    identity = ReferenceIdentity(
        mode="explicit",
        fasta="ref.fa",
        gtf="genes.gtf",
        fasta_sha256="a" * 64,
        gtf_sha256="b" * 64,
    )
    record = _minimal_record([_qc("pass")], events=[_OK_TASK])
    record2 = record.model_copy(update={"reference_identity": identity})
    restored = RunRecord.model_validate_json(record2.model_dump_json())
    assert restored.reference_identity is not None
    assert restored.reference_identity.mode == "explicit"
    assert restored.reference_identity.fasta == "ref.fa"
    assert restored.reference_identity.gtf_sha256 == "b" * 64


# ---------------------------------------------------------------------------
# Task B: harmonization provenance fields
# ---------------------------------------------------------------------------

def test_launch_manifest_round_trips_with_harmonized_reference_true():
    """harmonized_reference=True survives a JSON round-trip."""
    import json
    from contig.models import LaunchManifest

    manifest = LaunchManifest(
        run_id="run-2",
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        profiles=["docker"],
        backend="local",
        container_runtime="docker",
        input="/abs/sheet.csv",
        max_attempts=3,
        created_at="2026-06-30T00:00:00+00:00",
        harmonized_reference=True,
    )
    restored = LaunchManifest.model_validate_json(manifest.model_dump_json())
    assert restored.harmonized_reference is True


def test_launch_manifest_legacy_json_without_harmonized_reference_defaults_false():
    """A legacy launch.json that has no harmonized_reference field still loads."""
    import json
    from contig.models import LaunchManifest

    legacy_json = json.dumps({
        "run_id": "run-legacy",
        "pipeline": "nf-core/rnaseq",
        "revision": "3.26.0",
        "profiles": ["docker"],
        "backend": "local",
        "container_runtime": "docker",
        "input": None,
        "max_attempts": 3,
        "created_at": "2026-06-30T00:00:00+00:00",
    })
    manifest = LaunchManifest.model_validate_json(legacy_json)
    assert manifest.harmonized_reference is False


def test_reference_identity_round_trips_with_harmonization_fields():
    """harmonized=True and harmonized_direction='add_chr' survive a JSON round-trip."""
    from contig.models import ReferenceIdentity

    identity = ReferenceIdentity(
        mode="explicit",
        fasta="ref.fa",
        gtf="genes.gtf",
        harmonized=True,
        harmonized_direction="add_chr",
    )
    restored = ReferenceIdentity.model_validate_json(identity.model_dump_json())
    assert restored.harmonized is True
    assert restored.harmonized_direction == "add_chr"


def test_reference_identity_legacy_json_without_harmonization_fields_defaults():
    """A legacy ReferenceIdentity JSON without harmonization fields still loads."""
    import json
    from contig.models import ReferenceIdentity

    legacy_json = json.dumps({
        "mode": "explicit",
        "fasta": "ref.fa",
        "gtf": "genes.gtf",
    })
    identity = ReferenceIdentity.model_validate_json(legacy_json)
    assert identity.harmonized is False
    assert identity.harmonized_direction is None


def test_run_record_accepts_and_round_trips_harmonized_reference_direction():
    """harmonized_reference_direction='add_chr' survives a JSON round-trip."""
    from contig.models import RunRecord

    record = _minimal_record([_qc("pass")], events=[_OK_TASK])
    record2 = record.model_copy(update={"harmonized_reference_direction": "add_chr"})
    restored = RunRecord.model_validate_json(record2.model_dump_json())
    assert restored.harmonized_reference_direction == "add_chr"


def test_run_record_harmonized_reference_direction_defaults_to_none():
    """A RunRecord without harmonized_reference_direction defaults to None."""
    record = _minimal_record([_qc("pass")], events=[_OK_TASK])
    assert record.harmonized_reference_direction is None


def test_run_record_repair_history_defaults_empty_and_accepts_steps():
    from contig.models import RepairStep

    rec = _minimal_record([], events=[_OK_TASK])
    assert rec.repair_history == []
    step = RepairStep(
        attempt=1,
        diagnosis=__import__("contig.models", fromlist=["Diagnosis"]).Diagnosis(
            failure_class="unknown", root_cause="?", evidence=[], confidence=0.1
        ),
        patch=None,
        outcome="gave_up",
    )
    rec2 = _minimal_record([], events=[_OK_TASK])
    rec2.repair_history.append(step)
    assert rec2.repair_history[0].outcome == "gave_up"
