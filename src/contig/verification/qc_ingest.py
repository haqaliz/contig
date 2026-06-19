import json
from os import PathLike


def parse_multiqc_general_stats(text: str) -> dict[str, dict[str, float]]:
    data = json.loads(text)
    sections = data.get("report_general_stats_data", [])
    merged: dict[str, dict[str, float]] = {}
    for section in sections:
        for sample, metrics in section.items():
            merged.setdefault(sample, {})
            for metric, value in metrics.items():
                try:
                    merged[sample][metric] = float(value)
                except (TypeError, ValueError):
                    continue
    return merged


def parse_multiqc_general_stats_file(
    path: str | PathLike[str],
) -> dict[str, dict[str, float]]:
    with open(path, encoding="utf-8") as handle:
        return parse_multiqc_general_stats(handle.read())
