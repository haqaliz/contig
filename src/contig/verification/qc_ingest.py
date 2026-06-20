import json
from os import PathLike


def parse_multiqc_general_stats(text: str) -> dict[str, dict[str, float]]:
    data = json.loads(text)
    sections = data.get("report_general_stats_data", [])
    # Two MultiQC schemas in the wild: the legacy list `[{sample: {metric}}]`,
    # and the modern dict keyed by module `{module: {sample: {metric}}}` that
    # real nf-core output ships. Both reduce to a list of {sample: {metric}}
    # sections; merging across them gives one metric table per sample.
    if isinstance(sections, dict):
        sections = list(sections.values())
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
