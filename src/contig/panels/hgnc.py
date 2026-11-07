"""HGNC symbol resolution for panel building."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HgncIndex:
    approved: dict[str, str] = field(default_factory=dict)
    alias: dict[str, str] = field(default_factory=dict)
    version: str = ""


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        part.strip()
        for part in value.replace(",", "|").split("|")
        if part.strip() and part.strip() != "-"
    ]


def load_hgnc(path: str | Path) -> HgncIndex:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"HGNC file not found: {path}")

    approved: dict[str, str] = {}
    alias: dict[str, str] = {}
    with path.open("rt", newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            symbol = (row.get("symbol") or "").strip()
            if not symbol:
                continue
            approved.setdefault(symbol.upper(), symbol)
            for name in _split(row.get("alias_symbol")) + _split(row.get("prev_symbol")):
                key = name.upper()
                if key in approved and approved[key] != symbol:
                    alias.pop(key, None)
                    continue
                alias.setdefault(key, symbol)
    return HgncIndex(approved=approved, alias=alias, version=path.name)


def resolve_symbols(symbols: list[str], index: HgncIndex) -> tuple[list[str], list[str]]:
    approved: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        key = symbol.strip().upper()
        if not key:
            continue
        target = index.approved.get(key) or index.alias.get(key)
        if not target:
            unknown.append(symbol.strip())
            continue
        if target.upper() not in seen:
            seen.add(target.upper())
            approved.append(target)
    return approved, unknown
