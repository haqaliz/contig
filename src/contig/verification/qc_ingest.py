import json


def parse_multiqc_general_stats(text: str) -> dict[str, dict[str, float]]:
    data = json.loads(text)
    sections = data["report_general_stats_data"]
    merged: dict[str, dict[str, float]] = {}
    for section in sections:
        for sample, metrics in section.items():
            merged.setdefault(sample, {})
            for metric, value in metrics.items():
                merged[sample][metric] = float(value)
    return merged
