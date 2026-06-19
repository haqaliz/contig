"""The portable provenance bundle (ARCHITECTURE §7).

A bundle is the artifact that makes a run "re-runnable by a stranger": the full
RunRecord serialized to disk, plus the helper that derives the input checksums
that anchor it.
"""

from __future__ import annotations

from pathlib import Path

from contig.models import RunRecord, sha256_file


def write_bundle(record: RunRecord, dest_dir: str | Path) -> Path:
    """Serialize ``record`` to ``dest_dir/run_record.json`` and return that path."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / "run_record.json"
    json_path.write_text(record.model_dump_json(indent=2))
    return json_path


def load_bundle(dest_dir: str | Path) -> RunRecord:
    """Reconstruct the RunRecord from ``dest_dir/run_record.json``."""
    json_path = Path(dest_dir) / "run_record.json"
    return RunRecord.model_validate_json(json_path.read_text())


def compute_input_checksums(paths: list[str | Path]) -> dict[str, str]:
    """Map each input file's basename to its SHA-256, for RunRecord.input_checksums."""
    return {Path(p).name: sha256_file(p) for p in paths}
