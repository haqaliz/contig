import pytest

from contig.planner import PlanningError, plan


def _sheet(tmp_path, n_samples=2, paired=True):
    lines = ["sample,fastq_1,fastq_2,strandedness"]
    for i in range(n_samples):
        for r in (1, 2):
            (tmp_path / f"s{i}_R{r}.fastq.gz").write_bytes(b"x")
        r2 = f"s{i}_R2.fastq.gz" if paired else ""
        lines.append(f"S{i},s{i}_R1.fastq.gz,{r2},auto")
    sheet = tmp_path / "samplesheet.csv"
    sheet.write_text("\n".join(lines) + "\n")
    return sheet


def test_plan_selects_rnaseq_for_a_de_goal(tmp_path):
    p = plan("find differentially expressed genes", _sheet(tmp_path), reference_params={"genome": "GRCh38"})
    assert p.assay == "rnaseq"
    assert p.pipeline == "nf-core/rnaseq"
    assert p.revision == "3.26.0"
    assert p.params["genome"] == "GRCh38"
    assert p.params["input"]


def test_plan_clean_run_has_no_warnings(tmp_path):
    p = plan("RNA-seq differential expression", _sheet(tmp_path, n_samples=3), reference_params={"genome": "GRCh38"})
    assert p.warnings == []


def test_plan_warns_on_single_sample(tmp_path):
    p = plan("gene expression", _sheet(tmp_path, n_samples=1), reference_params={"genome": "GRCh38"})
    assert any("replicates" in w for w in p.warnings)


def test_plan_warns_when_no_reference(tmp_path):
    p = plan("RNA-seq DE", _sheet(tmp_path), reference_params=None)
    assert any("reference" in w.lower() for w in p.warnings)


def test_plan_raises_when_goal_unrecognized(tmp_path):
    with pytest.raises(PlanningError):
        plan("assemble a de novo bacterial genome", _sheet(tmp_path))
