"""A project manifest for building and checking several reports at once."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from contig.reporting.models import Template


class ProjectReport(BaseModel):
    id: str
    run_id: str
    runs_dir: str = "runs"
    variants: str | None = None
    readiness: str | None = None
    spec: str | None = None
    template: Template | None = None
    out: str | None = None
    meta: str | None = None
    bundle: bool = False

    @field_validator("id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class ProjectManifest(BaseModel):
    name: str = "project"
    out_dir: str = "reports"
    reports: list[ProjectReport] = Field(default_factory=list)


def load_project(path: str | Path) -> tuple[ProjectManifest, Path]:
    """Load a project manifest and the directory its relative paths resolve against."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"project manifest not found: {path}")
    manifest = ProjectManifest.model_validate_json(path.read_text(encoding="utf-8"))
    ids = [entry.id for entry in manifest.reports]
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate report id(s): {', '.join(duplicates)}")
    return manifest, path.resolve().parent


def resolve(base: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else base / path


def report_paths(
    manifest: ProjectManifest, entry: ProjectReport, base: Path
) -> tuple[Path, Path, Path]:
    """The output directory, HTML path, and sidecar path for one entry."""
    out_dir = resolve(base, manifest.out_dir) or base
    out = resolve(base, entry.out) if entry.out else out_dir / f"{entry.id}.html"
    meta = resolve(base, entry.meta) if entry.meta else out_dir / f"{entry.id}.json"
    return out_dir, out, meta
