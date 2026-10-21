"""Version pinning from a traced nf-core execution (C8-24).

nf-core emits one `versions.yml` per process under the Nextflow work dir, in a
narrow two-level shape::

    "NFCORE_RNASEQ:RNASEQ:BAM_QC_RNASEQ:DUPRADAR":
        bioconductor-dupradar: 1.38.0

`parse_versions_yml` reads only that shape (optional quotes, 2- or 4-space leaf)
with stdlib only; anything else is skipped rather than guessed. `collect_tool_versions`
walks a run's configured `work_dir` and merges every per-task file.

Rule for duplicates: a tool reported with two different versions is never
collapsed to one. All distinct versions are kept, sorted, and comma-joined
(`{"samtools": "1.19.2, 1.21"}`); the same version twice collapses.
"""

from __future__ import annotations

from pathlib import Path


def _merge(merged: dict[str, list[str]], tool: str, version: str) -> None:
    versions = merged.setdefault(tool, [])
    if version not in versions:
        versions.append(version)


def _render(merged: dict[str, list[str]]) -> dict[str, str]:
    # Sorting makes the value stable across work-dir walk order; it is a list of
    # observations, NOT a "max version" claim (no version ordering is guessed).
    return {tool: ", ".join(sorted(versions)) for tool, versions in merged.items()}


def parse_versions_yml(text: str) -> dict[str, str]:
    """Parse one nf-core `versions.yml` into `{tool: version}` (narrow, never raises).

    Only two levels are read: an unindented `PROCESS:` key, then its `tool: version`
    leaves indented by 2 or 4 spaces. Blank lines, comments, malformed rows and
    deeper nesting are skipped, so an unexpected layout yields fewer entries
    rather than a wrong one.
    """
    merged: dict[str, list[str]] = {}
    in_process = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            in_process = line.endswith(":")
            continue
        if not in_process or indent not in (2, 4):
            continue
        tool, _, version = line.strip().partition(":")
        tool = tool.strip().strip("\"'")
        version = version.strip().strip("\"'")
        if tool and version:
            _merge(merged, tool, version)
    return _render(merged)


def collect_tool_versions(work_dir: str | Path) -> dict[str, str]:
    """Merge every `versions.yml` under `work_dir` into `{tool: version}`.

    `work_dir` is the run's configured `ExecutionTarget.work_dir` (not a
    `<run_dir>/work` guess). A missing directory -- including a remote
    `s3://` work dir, which `Path` cannot see -- returns `{}`: no trace, no
    fabrication. An unreadable file costs only that file.
    """
    work = Path(work_dir)
    if not work.is_dir():
        return {}
    merged: dict[str, list[str]] = {}
    for path in sorted(work.glob("**/versions.yml")):
        try:
            text = path.read_text()
        except OSError:
            continue
        for tool, version in parse_versions_yml(text).items():
            for item in version.split(", "):
                _merge(merged, tool, item)
    return _render(merged)
