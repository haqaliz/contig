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


# --- Modern MultiQC schema -------------------------------------------------
# Real nf-core/rnaseq output ships `report_general_stats_data` as a dict keyed by
# MODULE (salmon, samtools, rseqc, ...), each holding {sample: {metric: value}} -
# not the legacy list. The parser must read both, merging a sample's metrics
# across modules. Shape and keys below are taken verbatim from a real run.
def test_modern_module_keyed_schema_merges_metrics_per_sample():
    text = json.dumps(
        {
            "report_general_stats_data": {
                "salmon": {"WT_REP1": {"percent_mapped": 80.98, "num_mapped": 40165}},
                "samtools": {"WT_REP1": {"reads_mapped_percent": 100.0}},
                "rseqc": {"WT_REP1": {"unique_percent": 82.76}},
            }
        }
    )
    result = parse_multiqc_general_stats(text)
    assert result == {
        "WT_REP1": {
            "percent_mapped": 80.98,
            "num_mapped": 40165.0,
            "reads_mapped_percent": 100.0,
            "unique_percent": 82.76,
        }
    }


def test_modern_schema_keeps_samples_separate_across_modules():
    text = json.dumps(
        {
            "report_general_stats_data": {
                "salmon": {
                    "WT_REP1": {"percent_mapped": 80.0},
                    "WT_REP2": {"percent_mapped": 30.0},
                },
                "samtools": {"WT_REP2": {"reads_mapped_percent": 55.0}},
            }
        }
    )
    result = parse_multiqc_general_stats(text)
    assert result == {
        "WT_REP1": {"percent_mapped": 80.0},
        "WT_REP2": {"percent_mapped": 30.0, "reads_mapped_percent": 55.0},
    }
