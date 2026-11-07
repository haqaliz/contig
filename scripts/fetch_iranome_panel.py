#!/usr/bin/env python3
"""Fetch a small Iranian allele-frequency panel from Iranome.

Iranome (https://www.iranome.com) is a public catalogue of exome variants from
1,200 Iranians across 12 ethnic groups. Its terms allow free use with citation:

    Fattahi Z, et al. Iranome: A catalog of genomic variations in the Iranian
    population. Hum Mutat. 2019;40(11):1968-1984.

The public site has no bulk download endpoint, so this script reads the
`window.table_variants` JSON embedded in each gene page. It is polite: one
request per gene, one second apart. Output is research-use only.

Usage:
    python scripts/fetch_iranome_panel.py [--out data/iranome]
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from pathlib import Path

GENES = [
    "BRCA1", "BRCA2", "PALB2", "TP53", "PTEN", "ATM", "CHEK2",
    "CFTR", "GJB2", "SMN1", "MLH1", "MSH2", "MSH6", "PMS2",
    "EGFR", "MYBPC3",
]

URL = "https://www.iranome.com/awesome?query={gene}"
USER_AGENT = "contig-research-data/0.1 (+https://github.com/haqaliz/contig)"
MARKER = "window.table_variants = "

COLUMNS = [
    "gene", "chrom", "pos", "ref", "alt", "rsid", "hgvsc", "hgvsp",
    "major_consequence", "category", "filter", "exon_num",
    "allele_count", "allele_num", "allele_freq", "hom_count", "het_count",
    "cadd_phred", "revel", "sift", "polyphen2_hvar", "pop_afs",
]


def extract_json_array(text: str, marker: str) -> list[dict]:
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"marker not found: {marker}")
    start += len(marker)
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unterminated JSON array")


def score(pred: dict, key: str) -> str:
    value = pred.get(key, "?")
    return "" if value in ("?", "", None) else str(value)


def fetch_gene(gene: str) -> list[dict]:
    request = urllib.request.Request(URL.format(gene=gene), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return extract_json_array(response.read().decode("utf-8", "replace"), MARKER)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/iranome")
    parser.add_argument("--genes", nargs="*", default=GENES)
    args = parser.parse_args()

    out = Path(args.out)
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for gene in args.genes:
        variants = fetch_gene(gene)
        (raw / f"{gene}.json").write_text(json.dumps(variants), encoding="utf-8")
        for v in variants:
            pred = v.get("dbnsfp_pred") or {}
            rows.append({
                "gene": v.get("gene_name", gene),
                "chrom": v.get("chrom", ""),
                "pos": v.get("pos", ""),
                "ref": v.get("ref", ""),
                "alt": v.get("alt", ""),
                "rsid": v.get("rsid", ""),
                "hgvsc": v.get("HGVSc", ""),
                "hgvsp": v.get("HGVSp", ""),
                "major_consequence": v.get("major_consequence", ""),
                "category": v.get("category", ""),
                "filter": v.get("filter", ""),
                "exon_num": v.get("exon_num", ""),
                "allele_count": v.get("allele_count", ""),
                "allele_num": v.get("allele_num", ""),
                "allele_freq": v.get("allele_freq", ""),
                "hom_count": v.get("hom_count", ""),
                "het_count": v.get("het_count", ""),
                "cadd_phred": score(pred, "CADD Score (Phred Scale)"),
                "revel": score(pred, " REVEL Score"),
                "sift": score(pred, "SIFT Pred (C)"),
                "polyphen2_hvar": score(pred, "Polyphen2 HVAR Pred (C)"),
                "pop_afs": json.dumps(v.get("pop_acs", {})),
            })
        print(f"{gene}: {len(variants)} variants")
        time.sleep(1)

    tsv = out / "iranome_panel.tsv"
    with tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {tsv}")


if __name__ == "__main__":
    main()
