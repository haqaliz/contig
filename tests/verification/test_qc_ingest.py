import json

from contig.verification.qc_ingest import (
    parse_multiqc_general_stats,
    parse_multiqc_general_stats_file,
)


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


def test_two_sections_same_sample_merged():
    text = json.dumps(
        {
            "report_general_stats_data": [
                {"SAMPLE_1": {"uniquely_mapped_percent": 92.5}},
                {"SAMPLE_1": {"percent_assigned": 88.0}},
            ]
        }
    )
    result = parse_multiqc_general_stats(text)
    assert result == {
        "SAMPLE_1": {"uniquely_mapped_percent": 92.5, "percent_assigned": 88.0}
    }


def test_two_samples_kept_separate():
    text = json.dumps(
        {
            "report_general_stats_data": [
                {
                    "SAMPLE_1": {"percent_assigned": 88.0},
                    "SAMPLE_2": {"percent_assigned": 45.0},
                }
            ]
        }
    )
    result = parse_multiqc_general_stats(text)
    assert result == {
        "SAMPLE_1": {"percent_assigned": 88.0},
        "SAMPLE_2": {"percent_assigned": 45.0},
    }


def test_integer_values_coerced_to_float():
    text = '{"report_general_stats_data": [{"SAMPLE_1": {"total_reads": 1000000}}]}'
    result = parse_multiqc_general_stats(text)
    value = result["SAMPLE_1"]["total_reads"]
    assert value == 1000000.0
    assert isinstance(value, float)


def test_non_numeric_metric_skipped():
    text = json.dumps(
        {
            "report_general_stats_data": [
                {"SAMPLE_1": {"strand": "forward", "percent_assigned": 88.0}}
            ]
        }
    )
    result = parse_multiqc_general_stats(text)
    assert result == {"SAMPLE_1": {"percent_assigned": 88.0}}


def test_missing_key_returns_empty_dict():
    text = json.dumps({"some_other_key": "value"})
    result = parse_multiqc_general_stats(text)
    assert result == {}


def test_parse_file_matches_text_parser(tmp_path):
    payload = {
        "report_general_stats_data": [
            {"SAMPLE_1": {"uniquely_mapped_percent": 92.5, "total_reads": 1000000.0}},
            {
                "SAMPLE_1": {"percent_assigned": 88.0},
                "SAMPLE_2": {"percent_assigned": 45.0, "uniquely_mapped_percent": 30.0},
            },
        ]
    }
    text = json.dumps(payload)
    path = tmp_path / "multiqc_data.json"
    path.write_text(text)

    assert parse_multiqc_general_stats_file(path) == parse_multiqc_general_stats(text)
