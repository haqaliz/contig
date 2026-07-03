"""Phase 7 (M8): end-to-end acceptance for the somatic variant-calling assay.

ONE integration test proving the assay is real end-to-end, not just unit-correct
at each seam: intake (a sarek tumor/normal sample sheet) -> plan/dispatch
(``--assay somatic_variant_calling``) -> run (an injected executor that writes a
synthetic sarek somatic output tree) -> verify (the somatic structural manifest
evaluated over the emitted VCF).

It reuses the established CLI-driven end-to-end pattern the germline/RNA-seq run
tests in ``test_cli.py`` use — monkeypatch ``contig.cli.default_executor`` and
drive ``contig run`` through ``CliRunner`` — so the whole
dispatch -> self_heal -> run_pipeline -> capture -> bundle path runs for real;
only the executor (the process that would shell out to Nextflow) is faked. No
real nf-core/sarek/samtools runs in CI (synthetic fixtures only).
"""

import gzip
from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import load_bundle
from contig.cli import app
from contig.methods import render_methods
from contig.verification.structural import evaluate_against_manifest, manifest_for

runner = CliRunner()

# A minimal, valid Nextflow trace with one COMPLETED task, so the captured record
# reports success (and the run's verdict is computed, not short-circuited to fail).
TRACE_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tNFCORE_SAREK:STRELKA_SOMATIC (T_vs_N)\tCOMPLETED\t0\t-\t-\t-\n"
)

# The synthetic sarek somatic output, at exactly the path sarek writes it:
# results/variant_calling/<caller>/<tumor>_vs_<normal>/*.somatic_snvs.vcf.gz
_SOMATIC_VCF_REL = (
    Path("variant_calling") / "strelka" / "T_vs_N" / "T_vs_N.strelka.somatic_snvs.vcf.gz"
)
_VCF_BYTES = b"##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"


def _somatic_sheet(tmp_path):
    """A valid sarek tumor/normal sheet: one patient P1 with a normal (status 0)
    and a tumor (status 1) row, backed by tiny real FASTQs on disk so the somatic
    pre-flight validator passes."""
    for name in ("n_R1.fastq.gz", "n_R2.fastq.gz", "t_R1.fastq.gz", "t_R2.fastq.gz"):
        (tmp_path / name).write_bytes(gzip.compress(b"@r\nACGT\n+\nIIII\n"))
    sheet = tmp_path / "samplesheet.csv"
    sheet.write_text(
        "patient,sample,status,lane,fastq_1,fastq_2\n"
        "P1,N,0,L001,n_R1.fastq.gz,n_R2.fastq.gz\n"
        "P1,T,1,L001,t_R1.fastq.gz,t_R2.fastq.gz\n"
    )
    return sheet


def _somatic_executor(captured):
    """A fake Nextflow executor: record the assembled argv, write a valid trace and
    a synthetic sarek somatic VCF (a real gzip/bgzip stream) under results/, then
    succeed. Mirrors the ``_fake_run_executor`` pattern in test_cli.py."""

    def execute(cmd, trace_path):
        captured["cmd"] = list(cmd)
        Path(trace_path).write_text(TRACE_OK)
        vcf = Path(trace_path).parent / "results" / _SOMATIC_VCF_REL
        vcf.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(vcf, "wb") as fh:  # a real, fully-decompressible gzip stream
            fh.write(_VCF_BYTES)
        return 0

    return execute


def test_somatic_run_end_to_end(tmp_path, monkeypatch):
    sheet = _somatic_sheet(tmp_path)
    runs_dir = tmp_path / "runs"
    captured: dict = {}
    monkeypatch.setattr("contig.cli.default_executor", _somatic_executor(captured))

    result = runner.invoke(
        app,
        [
            "run",
            "--run-id", "somatic1",
            "--runs-dir", str(runs_dir),
            "--pipeline", "nf-core/sarek",
            "--revision", "3.5.1",
            "--assay", "somatic_variant_calling",
            "--input", str(sheet),
            "--genome", "GRCh38",
        ],
    )
    assert result.exit_code == 0, result.output

    # (1) The assembled Nextflow command genuinely invokes sarek's somatic callers:
    # the per-assay default_params injected --tools strelka,mutect2 (M4).
    cmd = captured["cmd"]
    assert "--tools" in cmd
    assert cmd[cmd.index("--tools") + 1] == "strelka,mutect2"

    # (2) The run is labelled the somatic assay, persisted on the record (M2) — NOT
    # the pipeline-derived germline assay that nf-core/sarek would otherwise resolve.
    record = load_bundle(runs_dir / "somatic1")
    assert record.assay == "somatic_variant_calling"

    # (3) The somatic structural manifest (M5), evaluated over the run's REAL emitted
    # output tree (the executor's actual results dir, not a hand-built fixture),
    # recognizes the somatic VCF and passes structurally on it.
    results_dir = Path(record.parameters["outdir"])
    structural = evaluate_against_manifest(
        results_dir, manifest_for("somatic_variant_calling")
    )
    assert structural, "the somatic manifest evaluated to no checks over the outputs"
    vcf_name = _SOMATIC_VCF_REL.name
    assert any(vcf_name in r.check for r in structural)  # a result references the VCF
    assert all(r.kind == "structural" for r in structural)
    assert all(r.status == "pass" for r in structural)

    # (4) The run's own verdict is scoped and honest: with no somatic QC coverage in
    # the live loop, it is "unverified" — never a false "pass" on zero coverage.
    assert record.verdict == "unverified"
    assert record.verdict != "pass"

    # (5) The methods prose names the somatic assay (M6), not germline.
    methods = render_methods(record)
    assert "somatic" in methods.lower()
    assert "germline" not in methods.lower()
