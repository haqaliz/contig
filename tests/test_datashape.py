from contig.datashape import assay_expects_replicates, inspect_data_shape
from contig.samplesheet import SampleRow


def test_two_paired_end_rows():
    rows = [
        SampleRow(sample="s1", fastq_1="r1_1.fq.gz", fastq_2="r1_2.fq.gz"),
        SampleRow(sample="s2", fastq_1="r2_1.fq.gz", fastq_2="r2_2.fq.gz"),
    ]
    shape = inspect_data_shape(rows)
    assert shape.n_samples == 2
    assert shape.layout == "paired"
    assert shape.warnings == []


def test_all_single_end():
    rows = [
        SampleRow(sample="s1", fastq_1="r1.fq.gz"),
        SampleRow(sample="s2", fastq_1="r2.fq.gz"),
    ]
    shape = inspect_data_shape(rows)
    assert shape.layout == "single"
    assert any("single-end" in w for w in shape.warnings)


def test_mixed_layout():
    rows = [
        SampleRow(sample="s1", fastq_1="r1_1.fq.gz", fastq_2="r1_2.fq.gz"),
        SampleRow(sample="s2", fastq_1="r2.fq.gz"),
    ]
    shape = inspect_data_shape(rows)
    assert shape.layout == "mixed"
    assert any("mixed" in w for w in shape.warnings)


def test_one_sample_warns_replicates():
    rows = [SampleRow(sample="s1", fastq_1="r1_1.fq.gz", fastq_2="r1_2.fq.gz")]
    shape = inspect_data_shape(rows)
    assert shape.n_samples == 1
    assert any("replicates" in w for w in shape.warnings)


def test_one_sample_no_replicate_warning_when_not_expected():
    # single-sample germline variant calling is valid; no "needs replicates" warning
    rows = [SampleRow(sample="s1", fastq_1="r1_1.fq.gz", fastq_2="r1_2.fq.gz")]
    shape = inspect_data_shape(rows, expects_replicates=False)
    assert not any("replicates" in w for w in shape.warnings)


def test_rnaseq_expects_replicates():
    assert assay_expects_replicates("rnaseq") is True


def test_variant_calling_does_not_expect_replicates():
    assert assay_expects_replicates("variant_calling") is False


def test_scrnaseq_does_not_expect_bulk_replicates():
    # single-cell measures cells within a sample, not bulk replicates, so a
    # single scRNA sample must not raise the "needs replicates" warning
    assert assay_expects_replicates("scrnaseq") is False


def test_one_scrnaseq_sample_has_no_replicate_warning():
    rows = [SampleRow(sample="s1", fastq_1="r1_1.fq.gz", fastq_2="r1_2.fq.gz")]
    shape = inspect_data_shape(
        rows, expects_replicates=assay_expects_replicates("scrnaseq")
    )
    assert not any("replicates" in w for w in shape.warnings)


def test_clean_three_sample_paired_run_no_warnings():
    rows = [
        SampleRow(sample="s1", fastq_1="r1_1.fq.gz", fastq_2="r1_2.fq.gz"),
        SampleRow(sample="s2", fastq_1="r2_1.fq.gz", fastq_2="r2_2.fq.gz"),
        SampleRow(sample="s3", fastq_1="r3_1.fq.gz", fastq_2="r3_2.fq.gz"),
    ]
    shape = inspect_data_shape(rows)
    assert shape.n_samples == 3
    assert shape.layout == "paired"
    assert shape.warnings == []
