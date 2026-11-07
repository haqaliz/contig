"""Thin command layer for `contig variants`."""

from __future__ import annotations

from pathlib import Path

import typer

from contig.variants.models import FilterSpec
from contig.variants.table import (
    RESEARCH_USE_NOTICE,
    build_table,
    render_json,
    render_tsv,
    write_table,
)


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def run_variants(
    vcf: str,
    *,
    clinvar: str | None = None,
    iranome: str | None = None,
    frequencies: str | None = None,
    gnomad_api: bool = False,
    gnomad_cache: str | None = None,
    gnomad_dataset: str = "gnomad_r4",
    build: str | None = None,
    genes: str | None = None,
    consequences: str | None = None,
    max_af: float | None = None,
    clinvar_significance: str | None = None,
    pass_only: bool = False,
    min_depth: int | None = None,
    min_vaf: float | None = None,
    zygosity: str | None = None,
    region: str | None = None,
    spec_path: str | None = None,
    save_spec: str | None = None,
    out: str | None = None,
    json_out: bool = False,
) -> None:
    if build not in (None, "GRCh37", "GRCh38"):
        raise ValueError("build must be GRCh37 or GRCh38")

    explicit = FilterSpec(
        genes=_split(genes),
        consequences=_split(consequences),
        max_af=max_af,
        clinvar_significance=_split(clinvar_significance),
        pass_only=pass_only,
        min_depth=min_depth,
        min_vaf=min_vaf,
        zygosity=zygosity,
        region=region,
    )

    spec = explicit
    if spec_path:
        saved = FilterSpec.model_validate_json(Path(spec_path).read_text(encoding="utf-8"))
        spec = saved.merged(explicit)

    typer.echo(RESEARCH_USE_NOTICE, err=True)
    table = build_table(
        vcf,
        clinvar=clinvar,
        iranome=iranome,
        frequencies=frequencies,
        gnomad_api=gnomad_api,
        gnomad_cache=gnomad_cache,
        gnomad_dataset=gnomad_dataset,
        build=build,
        spec=spec,
    )

    if save_spec:
        Path(save_spec).write_text(table.meta.filters.model_dump_json(indent=2), encoding="utf-8")

    if out:
        write_table(table, out, as_json=json_out)
        typer.echo(f"Wrote {out}")
        return

    typer.echo(render_json(table) if json_out else render_tsv(table), nl=False)
