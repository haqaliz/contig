"""C5-2: pre-flight consistency between --known-sites contigs and the reference.

A known-sites resource built against a different assembly must not launch; a
partial overlap stays visible as a WARN breadcrumb (the reference-harmonization
channel), never a silent pass.
"""

import gzip
from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import load_bundle
from contig.cli import app
from contig.reference_check import vcf_contigs

runner = CliRunner()

VARIANT_MQC = '{"report_general_stats_data":[{"S1":{"ts_tv":2.05,"het_hom":1.6,"mean_coverage":35.0}}]}'

TRACE_RUN_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tSTAR (S1)\tCOMPLETED\t0\t-\t-\t-\n"
)


def _fake_run_executor():
    def execute(cmd, trace_path):
        Path(trace_path).write_text(TRACE_RUN_OK)
        d = Path(trace_path).parent / "results" / "multiqc"
        d.mkdir(parents=True, exist_ok=True)
        (d / "multiqc_data.json").write_text(VARIANT_MQC)
        return 0
    return execute


def _write_fasta(tmp_path, contigs):
    path = tmp_path / "ref.fa"
    path.write_text("".join(f">{c}\nACGT\n" for c in contigs))
    return path


def _write_gtf(tmp_path, contigs):
    path = tmp_path / "ref.gtf"
    path.write_text(
        "".join(
            f'{c}\tsource\tgene\t1\t100\t.\t+\t.\tgene_id "g{i}"\n'
            for i, c in enumerate(contigs)
        )
    )
    return path


def _write_vcf(tmp_path, contigs, *, header=True, name="known.vcf"):
    path = tmp_path / name
    lines = ["##fileformat=VCFv4.2\n"]
    if header:
        lines += [f"##contig=<ID={c},length=1000>\n" for c in contigs]
    lines.append("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
    for i, c in enumerate(contigs):
        lines.append(f"{c}\t{100 + i}\t.\tA\tT\t50\tPASS\t.\n")
    path.write_text("".join(lines))
    return path


def _write_sheet(tmp_path):
    (tmp_path / "s1_R1.fastq.gz").write_bytes(b"\x1f\x8bR1")
    (tmp_path / "s1_R2.fastq.gz").write_bytes(b"\x1f\x8bR2")
    sheet = tmp_path / "samplesheet.csv"
    sheet.write_text("sample,fastq_1,fastq_2,strandedness\nS1,s1_R1.fastq.gz,s1_R2.fastq.gz,auto\n")
    return sheet


def _invoke(tmp_path, fasta, gtf, known=None, run_id="ks"):
    args = [
        "run", "--run-id", run_id, "--runs-dir", str(tmp_path / "runs"),
        "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
        "--input", str(_write_sheet(tmp_path)),
        "--fasta", str(fasta), "--gtf", str(gtf),
        "--vep-cache", str(tmp_path / "vep"), "--snpeff-cache", str(tmp_path / "snpeff"),
    ]
    if known is not None:
        args += ["--dbsnp", str(known)]
    return runner.invoke(app, args)


# --- vcf_contigs ------------------------------------------------------------


def test_vcf_contigs_prefers_contig_header_lines(tmp_path):
    vcf = _write_vcf(tmp_path, ["chr1", "chr2"])
    assert vcf_contigs(vcf) == {"chr1", "chr2"}


def test_vcf_contigs_falls_back_to_first_column_without_header(tmp_path):
    vcf = _write_vcf(tmp_path, ["1", "2"], header=False)
    assert vcf_contigs(vcf) == {"1", "2"}


def test_vcf_contigs_reads_gzip(tmp_path):
    plain = _write_vcf(tmp_path, ["chr1", "chr2"])
    gz = tmp_path / "known.vcf.gz"
    with gzip.open(gz, "wt") as fh:
        fh.write(plain.read_text())
    assert vcf_contigs(gz) == {"chr1", "chr2"}


# --- pre-flight decisions ---------------------------------------------------


def test_identical_contigs_pass(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor())
    result = _invoke(
        tmp_path,
        _write_fasta(tmp_path, ["chr1", "chr2"]),
        _write_gtf(tmp_path, ["chr1", "chr2"]),
        _write_vcf(tmp_path, ["chr1", "chr2"]),
    )
    assert result.exit_code == 0
    rec = load_bundle(tmp_path / "runs" / "ks")
    assert not [q for q in rec.qc_results if q.check == "known_sites_contigs"]


def test_absent_known_sites_flag_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor())
    result = _invoke(
        tmp_path,
        _write_fasta(tmp_path, ["chr1", "chr2"]),
        _write_gtf(tmp_path, ["chr1", "chr2"]),
        run_id="noks",
    )
    assert result.exit_code == 0
    rec = load_bundle(tmp_path / "runs" / "noks")
    assert not [q for q in rec.qc_results if q.check == "known_sites_contigs"]
    assert "dbsnp" not in rec.parameters


def test_chr_prefixed_known_sites_match_bare_fasta_via_aliases(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor())
    result = _invoke(
        tmp_path,
        _write_fasta(tmp_path, ["1", "2"]),
        _write_gtf(tmp_path, ["1", "2"]),
        _write_vcf(tmp_path, ["chr1", "chr2"]),
    )
    assert result.exit_code == 0


def test_zero_overlap_refuses_before_launch_and_writes_no_run_dir(tmp_path, monkeypatch):
    launched = {"n": 0}

    def exec_spy(cmd, trace_path):
        launched["n"] += 1
        return _fake_run_executor()(cmd, trace_path)

    monkeypatch.setattr("contig.cli.default_executor", exec_spy)
    result = _invoke(
        tmp_path,
        _write_fasta(tmp_path, ["chr1", "chr2"]),
        _write_gtf(tmp_path, ["chr1"]),
        _write_vcf(tmp_path, ["chr3", "chr4"]),
        run_id="wrongbuild",
    )
    assert result.exit_code != 0
    assert "different assembly" in result.output
    assert "chr3" in result.output and "chr1" in result.output
    assert launched["n"] == 0
    assert not (tmp_path / "runs" / "wrongbuild").exists()


def test_partial_overlap_proceeds_with_warn_breadcrumb(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor())
    result = _invoke(
        tmp_path,
        _write_fasta(tmp_path, ["chr1", "chr2"]),
        _write_gtf(tmp_path, ["chr1"]),
        _write_vcf(tmp_path, ["chr1", "chr3"]),
        run_id="partial",
    )
    assert result.exit_code == 0
    rec = load_bundle(tmp_path / "runs" / "partial")
    warnings = [q for q in rec.qc_results if q.check == "known_sites_contigs"]
    assert len(warnings) == 1
    assert warnings[0].status == "warn"
    assert "chr3" in warnings[0].message


def test_unreadable_known_sites_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor())
    bad = tmp_path / "broken.vcf.gz"
    bad.write_bytes(b"not gzip at all")
    result = _invoke(
        tmp_path,
        _write_fasta(tmp_path, ["chr1"]),
        _write_gtf(tmp_path, ["chr1"]),
        bad,
        run_id="unreadable",
    )
    assert result.exit_code != 0
    assert str(bad) in result.output
    assert not (tmp_path / "runs" / "unreadable").exists()


def test_contig_less_known_sites_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor())
    empty = tmp_path / "empty.vcf"
    empty.write_text("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
    result = _invoke(
        tmp_path,
        _write_fasta(tmp_path, ["chr1"]),
        _write_gtf(tmp_path, ["chr1"]),
        empty,
        run_id="nocontigs",
    )
    assert result.exit_code != 0
    assert str(empty) in result.output
    assert "no contig" in result.output
    assert not (tmp_path / "runs" / "nocontigs").exists()
