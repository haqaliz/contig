"""Lift the GRCh37 Iranome table to GRCh38 with a UCSC chain file.

The chain parser is deliberately small and stdlib-only: it supports the
plus/plus chains used by the public hg19ToHg38 chain and refuses reverse-strand
chains (counted, never guessed). A variant is lifted only when its whole REF
interval falls inside one ungapped block; anything spanning a gap is unmapped.
"""

from __future__ import annotations

import csv
import gzip
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from contig.models import sha256_file
from contig.variants.vcf import normalize_chrom


@dataclass(frozen=True)
class _Block:
    source_chrom: str
    source_start: int
    source_end: int
    dest_chrom: str
    dest_start: int
    score: int


class ChainIndex:
    def __init__(self) -> None:
        self.blocks: dict[str, list[_Block]] = {}
        self.unsupported_chains = 0

    def add(self, block: _Block) -> None:
        self.blocks.setdefault(block.source_chrom, []).append(block)

    def lift(self, chrom: str, pos: int, length: int) -> tuple[str, int] | None:
        source0 = pos - 1
        source1 = source0 + max(1, length)
        candidates = [
            block
            for block in self.blocks.get(normalize_chrom(chrom), [])
            if block.source_start <= source0 and source1 <= block.source_end
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda block: block.score)
        return (
            best.dest_chrom,
            best.dest_start + (source0 - best.source_start) + 1,
        )


def _open_text(path: str | Path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", errors="replace")
    return path.open("rt", errors="replace")


def load_chain(path: str | Path) -> ChainIndex:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"chain file not found: {path}")
    index = ChainIndex()
    source_chrom = dest_chrom = ""
    source_pos = dest_pos = 0
    score = 0
    supported = False
    with _open_text(path) as handle:
        for line in handle:
            if not line.strip():
                continue
            fields = line.split()
            if fields[0] == "chain":
                if len(fields) < 12:
                    raise ValueError(f"malformed chain header: {line.strip()[:120]}")
                score = int(fields[1])
                # UCSC hg19ToHg38 chains use the OLD assembly as the target
                # (column 2) and the NEW assembly as the query (column 7).
                source_chrom = normalize_chrom(fields[2])
                source_pos = int(fields[5])
                dest_chrom = normalize_chrom(fields[7])
                dest_pos = int(fields[10])
                supported = fields[4] == "+" and fields[9] == "+"
                if not supported:
                    index.unsupported_chains += 1
                continue
            if not supported:
                continue
            try:
                size = int(fields[0])
                dt = int(fields[1]) if len(fields) > 1 else 0
                dq = int(fields[2]) if len(fields) > 2 else 0
            except ValueError as exc:
                raise ValueError(f"malformed chain block: {line.strip()[:120]}") from exc
            if size > 0:
                index.add(_Block(
                    source_chrom=source_chrom,
                    source_start=source_pos,
                    source_end=source_pos + size,
                    dest_chrom=dest_chrom,
                    dest_start=dest_pos,
                    score=score,
                ))
            source_pos += size + dt
            dest_pos += size + dq
    if not index.blocks:
        raise ValueError(f"chain file has no supported plus/plus blocks: {path}")
    return index


def _fieldnames(reader: csv.DictReader) -> dict[str, str]:
    if not reader.fieldnames:
        raise ValueError("Iranome table needs a header")
    return {name.strip().lower(): name for name in reader.fieldnames if name}


def lift_iranome(
    iranome_path: str | Path,
    chain_path: str | Path,
    out_path: str | Path,
) -> dict[str, object]:
    iranome_path = Path(iranome_path)
    out_path = Path(out_path)
    if not iranome_path.is_file():
        raise FileNotFoundError(f"Iranome table not found: {iranome_path}")
    index = load_chain(chain_path)

    with iranome_path.open("rt", newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = _fieldnames(reader)
        for key in ("chrom", "pos", "ref", "alt"):
            if key not in fields:
                raise ValueError(f"Iranome table is missing {key!r}")
        rows = list(reader)

    mapped = 0
    unmapped = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(reader.fieldnames or []), delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            try:
                pos = int(float(row[fields["pos"]]))
            except (KeyError, TypeError, ValueError):
                unmapped += 1
                continue
            ref = str(row.get(fields["ref"], "")) if "ref" in fields else ""
            length = len(ref) if ref not in {"", "-", "_"} else 1
            lifted = index.lift(str(row.get(fields["chrom"], "")), pos, length)
            if lifted is None:
                unmapped += 1
                continue
            row[fields["chrom"]], row[fields["pos"]] = lifted
            writer.writerow(row)
            mapped += 1

    sidecar = out_path.with_name(out_path.name + ".lift.json")
    payload = {
        "source": str(iranome_path),
        "source_sha256": sha256_file(iranome_path),
        "chain": str(chain_path),
        "chain_sha256": sha256_file(chain_path),
        "output": str(out_path),
        "output_sha256": sha256_file(out_path),
        "source_build": "GRCh37",
        "target_build": "GRCh38",
        "mapped": mapped,
        "unmapped": unmapped,
        "unsupported_chains": index.unsupported_chains,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {**payload, "sidecar": str(sidecar)}
