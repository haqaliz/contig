"""Tests for methylseq (Bismark) bisulfite-report parsers.

All fixtures in this file are synthetic inline strings written to ``tmp_path`` —
no real nf-core/methylseq run, no network. Each parser turns ONE Bismark report
kind into ``{slug: float}`` for the slugs the methylseq rule pack scores:
``percent_aligned``, ``percent_duplication``, ``percent_bs_conversion``. Phase 3
adds a belt-and-suspenders integration test against a committed realistic
fixture; these are the fast, isolated unit tests pinning the parsing logic.
"""

from __future__ import annotations

from pathlib import Path

from contig.verification.methylseq_metrics import (
    parse_bismark_alignment_report,
    parse_bismark_conversion_report,
    parse_bismark_dedup_report,
)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


# --------------------------------------------------------------------------- #
# Alignment report (`*_PE_report.txt` / `*_SE_report.txt`) — "Mapping
# efficiency:" is the headline mapping-rate line Bismark writes.
# --------------------------------------------------------------------------- #

_ALIGNMENT_REPORT = """\
Bismark report for: S1_R1.fastq.gz and S1_R2.fastq.gz (version: v0.24.1)
Bismark was run with Bowtie 2 against the bisulfite genome of /refs/ with the specified options: -q --score-min L,0,-0.2 -p 4

Final Alignment report
=======================
Sequence pairs analysed in total:	1000000
Number of paired-end alignments with a unique best hit:	789000
Mapping efficiency:	78.90%
Sequence pairs with no alignments under any condition:	150000
Sequence pairs did not map uniquely:	61000
"""


def test_alignment_report_extracts_mapping_efficiency(tmp_path: Path) -> None:
    path = _write(tmp_path, "S1_bismark_bt2_PE_report.txt", _ALIGNMENT_REPORT)
    out = parse_bismark_alignment_report(path)
    assert out == {"percent_aligned": 78.9}


def test_alignment_report_missing_field_returns_empty(tmp_path: Path) -> None:
    text = "Bismark report for: S1 (version: v0.24.1)\nSequence pairs analysed in total:\t1000000\n"
    path = _write(tmp_path, "S1_bismark_bt2_PE_report.txt", text)
    assert parse_bismark_alignment_report(path) == {}


def test_alignment_report_non_numeric_value_is_omitted(tmp_path: Path) -> None:
    text = "Mapping efficiency:\tN/A\n"
    path = _write(tmp_path, "S1_bismark_bt2_PE_report.txt", text)
    assert parse_bismark_alignment_report(path) == {}


def test_alignment_report_unrecognized_file_returns_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, "unrelated.txt", "nothing to see here\n")
    assert parse_bismark_alignment_report(path) == {}


# --------------------------------------------------------------------------- #
# Deduplication report — "duplicated alignments removed:" with a parenthesized
# percentage is the field deduplicate_bismark writes.
# --------------------------------------------------------------------------- #

_DEDUP_REPORT = """\
Total number of alignments analysed in S1_bismark_bt2_pe.bam:	789000
Total number duplicated alignments removed:	97335 (12.34%)
Duplicated alignments were found at:	97335 different position(s)

Total count of deduplicated leftover sequences: 691665 (87.66% of total)
"""


def test_dedup_report_extracts_duplication_percent(tmp_path: Path) -> None:
    path = _write(tmp_path, "S1_bismark_bt2_pe.deduplication_report.txt", _DEDUP_REPORT)
    out = parse_bismark_dedup_report(path)
    assert out == {"percent_duplication": 12.34}


def test_dedup_report_missing_field_returns_empty(tmp_path: Path) -> None:
    text = "Total number of alignments analysed in S1.bam:\t789000\n"
    path = _write(tmp_path, "S1.deduplication_report.txt", text)
    assert parse_bismark_dedup_report(path) == {}


def test_dedup_report_non_numeric_value_is_omitted(tmp_path: Path) -> None:
    text = "Total number duplicated alignments removed:\tsome (N/A%)\n"
    path = _write(tmp_path, "S1.deduplication_report.txt", text)
    assert parse_bismark_dedup_report(path) == {}


def test_dedup_report_unrecognized_file_returns_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, "unrelated.txt", "nothing to see here\n")
    assert parse_bismark_dedup_report(path) == {}


# --------------------------------------------------------------------------- #
# Conversion / splitting report — a bisulfite conversion rate is ONLY emitted
# when an explicit conversion/control line is present. A standard splitting
# report (methylation-context percentages, no conversion/control line) MUST
# omit the slug rather than guess a value from an unrelated field.
# --------------------------------------------------------------------------- #

_CONVERSION_REPORT_WITH_CONTROL = """\
Bismark methylation extractor report for S1_bismark_bt2_pe.bam

Bisulfite conversion rate:	99.30%
Total number of C's analysed:	5000000
"""

_STANDARD_SPLITTING_REPORT = """\
Bismark methylation extractor report for S1_bismark_bt2_pe.bam

Total number of C's analysed:	5000000

Total methylated C's in CpG context:	120000
Total methylated C's in CHG context:	3000
Total methylated C's in CHH context:	4000
Total unmethylated C's in CpG context:	880000
Total unmethylated C's in CHG context:	1990000
Total unmethylated C's in CHH context:	2003000

C methylated in CpG context:	12.0%
C methylated in CHG context:	0.2%
C methylated in CHH context:	0.2%
"""


def test_conversion_report_with_control_line_extracts_rate(tmp_path: Path) -> None:
    path = _write(tmp_path, "S1_splitting_report.txt", _CONVERSION_REPORT_WITH_CONTROL)
    out = parse_bismark_conversion_report(path)
    assert out == {"percent_bs_conversion": 99.3}


def test_standard_splitting_report_without_control_line_is_empty(tmp_path: Path) -> None:
    # No conversion/control line present -> omitted, never guessed from the
    # methylation-context percentages that ARE present.
    path = _write(tmp_path, "S1_splitting_report.txt", _STANDARD_SPLITTING_REPORT)
    assert parse_bismark_conversion_report(path) == {}


def test_conversion_report_unrecognized_file_returns_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, "unrelated.txt", "nothing to see here\n")
    assert parse_bismark_conversion_report(path) == {}
