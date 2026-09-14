import json
from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import load_bundle
from contig.cli import app


runner = CliRunner()

VARIANT_MQC = '{"report_general_stats_data":[{"S1":{"ts_tv":2.05,"het_hom":1.6,"mean_coverage":35.0}}]}'

TRACE_RUN_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tSTAR (S1)\tCOMPLETED\t0\t-\t-\t-\n"
)


def _fake_run_executor(trace_text, mqc_json=None):
    def execute(cmd, trace_path):
        Path(trace_path).write_text(trace_text)
        if mqc_json is not None:
            d = Path(trace_path).parent / "results" / "multiqc"
            d.mkdir(parents=True, exist_ok=True)
            (d / "multiqc_data.json").write_text(mqc_json)
        return 0 if mqc_json is not None else 1
    return execute


def test_run_known_sites_flags_land_in_params_and_argv(tmp_path, monkeypatch):
    argv = []

    def exec_spy(cmd, trace_path):
        argv.append(cmd)
        return _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC)(cmd, trace_path)

    monkeypatch.setattr("contig.cli.default_executor", exec_spy)
    result = runner.invoke(
        app,
        ["run", "--run-id", "ks", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--dbsnp", "d.vcf.gz", "--known-indels", "i.vcf.gz",
         "--known-snps", "s.vcf.gz"],
    )
    assert result.exit_code == 0
    rec = load_bundle(tmp_path / "ks")
    assert rec.parameters["dbsnp"] == "d.vcf.gz"
    assert rec.parameters["known_indels"] == "i.vcf.gz"
    assert rec.parameters["known_snps"] == "s.vcf.gz"
    cmd = argv[0]
    for key, value in (("dbsnp", "d.vcf.gz"),
                       ("known_indels", "i.vcf.gz"),
                       ("known_snps", "s.vcf.gz")):
        flag = f"--{key}"
        assert flag in cmd
        assert cmd[cmd.index(flag) + 1] == value


def test_run_refuses_known_sites_flags_on_non_variant_assay(tmp_path, monkeypatch):
    launched = {"n": 0}

    def exec_spy(cmd, trace_path):
        launched["n"] += 1
        return _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC)(cmd, trace_path)

    monkeypatch.setattr("contig.cli.default_executor", exec_spy)
    result = runner.invoke(
        app,
        ["run", "--run-id", "ksbad", "--runs-dir", str(tmp_path),
         "--dbsnp", "d.vcf.gz"],
    )
    assert result.exit_code != 0
    assert "only valid for the variant_calling assay" in result.output
    assert "rnaseq" in result.output
    assert launched["n"] == 0  # refused pre-launch
    assert not (tmp_path / "ksbad" / "launch.json").exists()


def test_run_refuses_known_sites_flags_on_somatic_variant_calling(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "kssom", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling",
         "--known-snps", "s.vcf.gz"],
    )
    assert result.exit_code != 0
    assert "only valid for the variant_calling assay" in result.output
    assert "somatic_variant_calling" in result.output
    assert not (tmp_path / "kssom" / "launch.json").exists()


def test_run_warns_on_missing_known_sites_path_but_proceeds(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC))
    missing = tmp_path / "nope" / "dbsnp_146.hg38.vcf.gz"
    result = runner.invoke(
        app,
        ["run", "--run-id", "kswarn", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--dbsnp", str(missing)],
    )
    assert result.exit_code == 0  # warning, not a refusal
    assert f"Warning: known-sites file does not exist: {missing}" in result.output
    rec = load_bundle(tmp_path / "kswarn")
    assert rec.parameters["dbsnp"] == str(missing)  # still recorded for provenance


def test_run_repeated_known_sites_flag_last_value_wins(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "ksdup", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--dbsnp", "first.vcf.gz", "--dbsnp", "second.vcf.gz"],
    )
    assert result.exit_code == 0
    rec = load_bundle(tmp_path / "ksdup")
    assert rec.parameters["dbsnp"] == "second.vcf.gz"


def test_run_without_known_sites_flags_has_no_known_sites_params(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, VARIANT_MQC))
    result = runner.invoke(
        app,
        ["run", "--run-id", "ksnone", "--runs-dir", str(tmp_path),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1"],
    )
    assert result.exit_code == 0
    rec = load_bundle(tmp_path / "ksnone")
    for key in ("dbsnp", "known_indels", "known_snps"):
        assert key not in rec.parameters