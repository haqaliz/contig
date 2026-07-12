"""STARsolo second-quantifier seam for single-cell concordance autorun (Phase 1).

These tests cover the pure argv builder (`starsolo_command`), the pure CB/cDNA
read-order derivation (`readfiles_order` — the footgun), the chemistry preset
table (`chemistry_geometry`), and the runner's honest error paths. STAR is NEVER
executed here: the subprocess success path is intentionally out of CI, behind a
manual gate. Real files only, via tmp_path.
"""

import pytest

from contig.verification.sc_count_quantifier import (
    SecondScQuantifierError,
    chemistry_geometry,
    readfiles_order,
    run_starsolo_quantifier,
    starsolo_command,
)


# --- AC3: chemistry presets ------------------------------------------------


def test_chemistry_geometry_10xv3_values():
    assert chemistry_geometry("10xv3") == (1, 16, 17, 12)


def test_chemistry_geometry_10xv2_values():
    assert chemistry_geometry("10xv2") == (1, 16, 17, 10)


def test_chemistry_geometry_unknown_raises():
    with pytest.raises(SecondScQuantifierError) as excinfo:
        chemistry_geometry("nanopore-v9")
    assert "nanopore-v9" in str(excinfo.value)


# --- AC2: read-order derivation (the footgun) ------------------------------


def test_readfiles_order_swaps_pair():
    # Sample sheet yields [fastq_1(CB/R1), fastq_2(cDNA/R2)]; STARsolo wants
    # (cDNA, CB) = (fastqs[1], fastqs[0]).
    assert readfiles_order(["CB_R1.fastq.gz", "cDNA_R2.fastq.gz"]) == (
        "cDNA_R2.fastq.gz",
        "CB_R1.fastq.gz",
    )


def test_readfiles_order_uses_first_pair_when_more_than_two():
    fastqs = [
        "CB_R1.fastq.gz",
        "cDNA_R2.fastq.gz",
        "extra_R1.fastq.gz",
        "extra_R2.fastq.gz",
    ]
    assert readfiles_order(fastqs) == ("cDNA_R2.fastq.gz", "CB_R1.fastq.gz")


def test_readfiles_order_too_few_raises():
    with pytest.raises(SecondScQuantifierError):
        readfiles_order(["only_one_R1.fastq.gz"])


# --- AC1: pure argv builder (asserted without executing STAR) --------------


def test_starsolo_command_builds_expected_argv(tmp_path):
    cb = tmp_path / "s1_R1.fastq.gz"  # fastq_1 = CB / barcode read
    cdna = tmp_path / "s1_R2.fastq.gz"  # fastq_2 = cDNA read
    index = tmp_path / "star_genome_dir"
    whitelist = tmp_path / "whitelist.txt"
    out_dir = tmp_path / "out"

    # fastqs arrive in sample-sheet order [CB, cDNA]; the builder must swap them.
    argv = starsolo_command(
        [str(cb), str(cdna)], str(index), str(whitelist), "10xv3", str(out_dir)
    )

    assert argv[0] == "STAR"
    assert "--runMode" in argv
    assert argv[argv.index("--runMode") + 1] == "alignReads"
    assert argv[argv.index("--soloType") + 1] == "CB_UMI_Simple"
    assert argv[argv.index("--genomeDir") + 1] == str(index)
    assert argv[argv.index("--soloCBwhitelist") + 1] == str(whitelist)

    # 10x-v3 geometry.
    assert argv[argv.index("--soloCBstart") + 1] == "1"
    assert argv[argv.index("--soloCBlen") + 1] == "16"
    assert argv[argv.index("--soloUMIstart") + 1] == "17"
    assert argv[argv.index("--soloUMIlen") + 1] == "12"

    # The footgun: --readFilesIn must be cDNA THEN CB (reverse of the sheet).
    rf = argv.index("--readFilesIn")
    assert argv[rf + 1] == str(cdna)
    assert argv[rf + 2] == str(cb)

    assert argv[argv.index("--soloFeatures") + 1] == "Gene"
    assert argv[argv.index("--outSAMtype") + 1] == "None"
    assert argv[argv.index("--outFileNamePrefix") + 1] == f"{out_dir}/"


def test_starsolo_command_honors_10xv2_geometry(tmp_path):
    cb = tmp_path / "s1_R1.fastq.gz"
    cdna = tmp_path / "s1_R2.fastq.gz"
    argv = starsolo_command(
        [str(cb), str(cdna)], "idx", "wl", "10xv2", "out"
    )
    assert argv[argv.index("--soloUMIlen") + 1] == "10"


# --- AC4: runner error paths (STAR never really runs) ----------------------


def _write_samplesheet(tmp_path):
    r1 = tmp_path / "s1_R1.fastq.gz"
    r1.write_text("")
    r2 = tmp_path / "s1_R2.fastq.gz"
    r2.write_text("")
    sheet = tmp_path / "samplesheet.csv"
    sheet.write_text(
        "sample,fastq_1,fastq_2,strandedness\nS1,s1_R1.fastq.gz,s1_R2.fastq.gz,auto\n"
    )
    return sheet


def _valid_inputs(tmp_path):
    reads = _write_samplesheet(tmp_path)
    index = tmp_path / "star_genome_dir"
    index.mkdir()
    whitelist = tmp_path / "whitelist.txt"
    whitelist.write_text("AAACCCAAAGGG\n")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    return reads, index, whitelist, out_dir


def test_missing_binary_raises(tmp_path, monkeypatch):
    reads, index, whitelist, out_dir = _valid_inputs(tmp_path)
    monkeypatch.setattr(
        "contig.verification.sc_count_quantifier._STAR",
        "STAR-does-not-exist-xyz",
    )
    with pytest.raises(SecondScQuantifierError) as excinfo:
        run_starsolo_quantifier(
            str(reads), str(index), str(whitelist), "10xv3", str(out_dir)
        )
    assert "STAR" in str(excinfo.value)


def test_nonzero_exit_raises(tmp_path, monkeypatch):
    reads, index, whitelist, out_dir = _valid_inputs(tmp_path)
    # `false` exits nonzero and ignores its args; STARsolo itself never runs.
    monkeypatch.setattr(
        "contig.verification.sc_count_quantifier._STAR", "false"
    )
    with pytest.raises(SecondScQuantifierError):
        run_starsolo_quantifier(
            str(reads), str(index), str(whitelist), "10xv3", str(out_dir)
        )


def test_missing_matrix_output_raises(tmp_path, monkeypatch):
    reads, index, whitelist, out_dir = _valid_inputs(tmp_path)
    # `true` exits 0 and writes nothing, so no Solo matrix.mtx appears.
    monkeypatch.setattr(
        "contig.verification.sc_count_quantifier._STAR", "true"
    )
    with pytest.raises(SecondScQuantifierError) as excinfo:
        run_starsolo_quantifier(
            str(reads), str(index), str(whitelist), "10xv3", str(out_dir)
        )
    assert "matrix" in str(excinfo.value).lower()


def test_missing_reads_raises(tmp_path):
    _, index, whitelist, out_dir = _valid_inputs(tmp_path)
    missing = tmp_path / "nope.csv"
    with pytest.raises(SecondScQuantifierError) as excinfo:
        run_starsolo_quantifier(
            str(missing), str(index), str(whitelist), "10xv3", str(out_dir)
        )
    assert "reads" in str(excinfo.value).lower()


def test_missing_index_raises(tmp_path):
    reads, _, whitelist, out_dir = _valid_inputs(tmp_path)
    missing_index = tmp_path / "no-index"
    with pytest.raises(SecondScQuantifierError) as excinfo:
        run_starsolo_quantifier(
            str(reads), str(missing_index), str(whitelist), "10xv3", str(out_dir)
        )
    assert "index" in str(excinfo.value).lower()


def test_missing_whitelist_raises(tmp_path):
    reads, index, _, out_dir = _valid_inputs(tmp_path)
    missing_whitelist = tmp_path / "no-whitelist.txt"
    with pytest.raises(SecondScQuantifierError) as excinfo:
        run_starsolo_quantifier(
            str(reads), str(index), str(missing_whitelist), "10xv3", str(out_dir)
        )
    assert "whitelist" in str(excinfo.value).lower()


def test_malformed_reads_sheet_raises(tmp_path):
    # Sheet exists but lacks the required `fastq_1` column, so `fastq_paths`
    # raises a bare ValueError; the runner must fold it into the named error.
    reads = tmp_path / "malformed.csv"
    reads.write_text("sample,strandedness\nS1,auto\n")
    index = tmp_path / "star_genome_dir"
    index.mkdir()
    whitelist = tmp_path / "whitelist.txt"
    whitelist.write_text("AAACCCAAAGGG\n")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with pytest.raises(SecondScQuantifierError):
        run_starsolo_quantifier(
            str(reads), str(index), str(whitelist), "10xv3", str(out_dir)
        )
