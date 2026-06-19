import json

from contig.verification.qc_ingest import parse_multiqc_general_stats


def test_single_section_single_sample():
    text = json.dumps(
        {
            "report_general_stats_data": [
                {"SAMPLE_1": {"uniquely_mapped_percent": 92.5, "total_reads": 1000000.0}}
            ]
        }
    )
    result = parse_multiqc_general_stats(text)
    assert result == {
        "SAMPLE_1": {"uniquely_mapped_percent": 92.5, "total_reads": 1000000.0}
    }
