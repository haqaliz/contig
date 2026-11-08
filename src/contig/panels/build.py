"""Build canonical panel BEDs from genes or an existing BED, and read the registry."""

from __future__ import annotations

import gzip
import hashlib
import re
import shutil
from collections import defaultdict
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from contig.models import sha256_file
from contig.panels.hgnc import HgncIndex, load_hgnc, resolve_symbols
from contig.panels.models import Panel, PanelMeta, PanelSource
from contig.variants.vcf import normalize_chrom

PanelRow = tuple[str, int, int, str, str, str]


def _open_text(path: str | Path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", errors="replace")
    return path.open("rt", errors="replace")


def _contig_version() -> str:
    try:
        return pkg_version("contig")
    except PackageNotFoundError:
        return "unknown"


def _chrom_sort(chrom: str) -> tuple[int, str]:
    match = re.fullmatch(r"(\d+)(.*)", chrom)
    if match:
        return (int(match.group(1)), match.group(2))
    order = {"X": 23, "Y": 24, "MT": 25}
    return (order.get(chrom, 26), chrom)


def canonical_bed(rows: list[PanelRow]) -> str:
    unique = sorted(
        set(rows),
        key=lambda row: (_chrom_sort(row[0]), row[1], row[2], row[3], row[4], row[5]),
    )
    return "".join("\t".join(map(str, row)) + "\n" for row in unique)


def panel_id(name: str, bed_text: str, version: str = "1") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "panel"
    version_slug = re.sub(r"[^a-z0-9]+", "-", version.lower()).strip("-") or "1"
    digest = hashlib.sha256(bed_text.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-v{version_slug}-{digest}"


def _meta(
    name: str,
    build: str,
    source: str,
    bed_text: str,
    version: str = "1",
    sources: list[PanelSource] | None = None,
    **kwargs,
) -> PanelMeta:
    return PanelMeta(
        id=panel_id(name, bed_text, version),
        name=name,
        build=build,
        source=source,
        version=version,
        checksum=hashlib.sha256(bed_text.encode("utf-8")).hexdigest(),
        sources=sources or [],
        contig_version=_contig_version(),
        **kwargs,
    )


def build_from_bed(path: str | Path, name: str, build: str = "GRCh38", version: str = "1") -> Panel:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"panel BED not found: {path}")

    rows: list[PanelRow] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "track", "browser")):
            continue
        fields = stripped.split("\t")
        if len(fields) < 3:
            fields = stripped.split()
        if len(fields) < 3:
            continue
        try:
            start, end = int(fields[1]), int(fields[2])
        except ValueError:
            continue
        if end <= start:
            continue
        chrom = normalize_chrom(fields[0])
        label = fields[3] if len(fields) > 3 and fields[3] not in ("", ".") else f"{chrom}:{start}-{end}"
        rows.append((chrom, start, end, label, "", ""))

    if not rows:
        raise ValueError(f"no valid BED intervals in {path}")
    bed_text = canonical_bed(rows)
    return Panel(
        meta=_meta(
            name,
            build,
            "bed",
            bed_text,
            version=version,
            method="canonicalized BED",
            sources=[
                PanelSource(kind="bed", path=str(path), sha256=sha256_file(path))
            ],
            notes=[f"Source BED: {path}"],
        ),
        bed_text=bed_text,
    )


def _parse_gtf(path: str | Path, genes: set[str], transcripts: str) -> tuple[list[PanelRow], list[str]]:
    rows: list[PanelRow] = []
    transcripts_seen: set[str] = set()
    by_gene: dict[str, list[tuple[str, int, int, str, str, str, bool]]] = defaultdict(list)

    with _open_text(path) as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 9 or fields[2] != "exon":
                continue
            attrs: dict[str, str] = {}
            for item in fields[8].split(";"):
                item = item.strip()
                if " " in item:
                    key, value = item.split(" ", 1)
                    attrs[key] = value.strip('"')
            gene = attrs.get("gene_name", "")
            if gene.upper() not in genes:
                continue
            if attrs.get("transcript_type") not in (None, "protein_coding"):
                continue
            try:
                start, end = int(fields[3]) - 1, int(fields[4])
            except ValueError:
                continue
            if end <= start:
                continue
            transcript = attrs.get("transcript_id", "")
            exon = attrs.get("exon_number", "")
            by_gene[gene].append((
                normalize_chrom(fields[0]), start, end, gene, transcript, exon,
                "MANE_Select" in fields[8],
            ))

    for gene, gene_rows in by_gene.items():
        use = gene_rows
        if transcripts == "mane":
            mane = [row for row in gene_rows if row[6]]
            use = mane if mane else gene_rows
        for chrom, start, end, _gene, transcript, _exon, _mane in use:
            rows.append((chrom, start, end, gene, gene, transcript))
            if transcript:
                transcripts_seen.add(transcript)
    return rows, sorted(transcripts_seen)


def build_from_genes(
    genes: list[str],
    gtf_path: str | Path,
    *,
    name: str,
    build: str = "GRCh38",
    hgnc_path: str | Path | None = None,
    transcripts: str = "mane",
    version: str = "1",
) -> Panel:
    if transcripts not in {"mane", "all"}:
        raise ValueError("transcripts must be 'mane' or 'all'")
    if not genes:
        raise ValueError("at least one gene is required")

    notes: list[str] = []
    sources = [
        PanelSource(kind="gtf", path=str(gtf_path), sha256=sha256_file(gtf_path))
    ]
    if hgnc_path:
        index: HgncIndex = load_hgnc(hgnc_path)
        approved, unknown = resolve_symbols(genes, index)
        if unknown:
            raise ValueError(f"unknown HGNC symbol(s): {', '.join(unknown)}")
        sources.append(
            PanelSource(kind="hgnc", path=str(hgnc_path), sha256=sha256_file(hgnc_path))
        )
        notes.append(f"HGNC validated against {index.version}")
    else:
        approved = sorted({gene.strip().upper() for gene in genes if gene.strip()})
        notes.append("HGNC not supplied; symbols were not alias-normalized")

    rows, transcript_ids = _parse_gtf(gtf_path, set(approved), transcripts)
    if not rows:
        raise ValueError(f"no exons found for gene(s): {', '.join(approved)}")

    bed_text = canonical_bed(rows)
    method = (
        "GENCODE/GTF exons (MANE Select preferred)"
        if transcripts == "mane"
        else "GENCODE/GTF exons (all protein-coding transcripts)"
    )
    return Panel(
        meta=_meta(
            name,
            build,
            "genes",
            bed_text,
            version=version,
            genes=approved,
            transcripts=transcript_ids,
            method=method,
            sources=sources,
            notes=notes,
        ),
        bed_text=bed_text,
    )


def write_panel(panel: Panel, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bed_path = out / f"{panel.meta.id}.bed"
    meta_path = out / f"{panel.meta.id}.json"
    bed_path.write_text(panel.bed_text, encoding="utf-8")
    meta_path.write_text(panel.meta.model_dump_json(indent=2), encoding="utf-8")
    return bed_path, meta_path


def list_panels(directory: str | Path) -> list[PanelMeta]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    panels: list[PanelMeta] = []
    for path in sorted(directory.glob("*.json")):
        try:
            panels.append(PanelMeta.model_validate_json(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    panels.sort(key=lambda meta: (meta.name.lower(), meta.id))
    return panels


def load_panel(directory: str | Path, panel_id_value: str) -> Panel:
    directory = Path(directory)
    meta_path = directory / f"{panel_id_value}.json"
    bed_path = directory / f"{panel_id_value}.bed"
    if not meta_path.is_file() or not bed_path.is_file():
        raise FileNotFoundError(f"panel not found: {panel_id_value} in {directory}")
    meta = PanelMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    bed_text = bed_path.read_text(encoding="utf-8")
    checksum = hashlib.sha256(bed_text.encode("utf-8")).hexdigest()
    if checksum != meta.checksum:
        raise ValueError(f"panel BED checksum does not match its metadata: {panel_id_value}")
    return Panel(meta=meta, bed_text=bed_text)


def archive_panel(directory: str | Path, panel_id_value: str) -> tuple[Path, Path]:
    """Move a panel's BED and metadata into ``<directory>/archive``.

    The panel is checksum-validated first. ``list_panels`` only reads the top
    level, so an archived panel disappears from the active registry while staying
    loadable with ``--dir <directory>/archive``. Never overwrites an archived copy.
    """
    directory = Path(directory)
    load_panel(directory, panel_id_value)
    archive = directory / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    bed_path = directory / f"{panel_id_value}.bed"
    meta_path = directory / f"{panel_id_value}.json"
    dest_bed = archive / bed_path.name
    dest_meta = archive / meta_path.name
    if dest_bed.exists() or dest_meta.exists():
        raise ValueError(f"panel already archived: {panel_id_value}")
    shutil.move(str(bed_path), dest_bed)
    shutil.move(str(meta_path), dest_meta)
    return dest_bed, dest_meta
