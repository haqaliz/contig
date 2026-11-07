#!/usr/bin/env python3
"""Build a small multi-sample trio VCF from the GIAB Ashkenazim trio.

Uses `tabix` for region extraction; no Python VCF dependency. The output is a
real-data manual fixture for `contig family` (not a CI test).
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = {
    "HG002": ROOT / "data/giab/HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz",
    "HG003": ROOT / "data/giab/HG003_GRCh38_1_22_v4.2.1_benchmark.vcf.gz",
    "HG004": ROOT / "data/giab/HG004_GRCh38_1_22_v4.2.1_benchmark.vcf.gz",
}


def _gt(format_value: str, sample_value: str) -> str:
    keys = format_value.split(":")
    values = sample_value.split(":")
    if "GT" not in keys:
        return "./."
    index = keys.index("GT")
    return values[index] if index < len(values) and values[index] else "./."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="chr20:1000000-1200000")
    parser.add_argument("--out", default="data/giab/AshkenazimTrio_chr20_subset.vcf")
    args = parser.parse_args()

    sites: dict[tuple[str, str, str, str], dict[str, str]] = {}
    ids: dict[tuple[str, str, str, str], str] = {}

    for sample, path in SAMPLES.items():
        result = subprocess.run(
            ["tabix", str(path), args.region],
            check=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 10:
                continue
            chrom, pos, ident, ref, alt, _qual, _filter, _info, fmt, value = fields[:10]
            for alt_allele in alt.split(","):
                key = (chrom, pos, ref, alt_allele)
                sites.setdefault(key, {})[sample] = _gt(fmt, value)
                ids.setdefault(key, ident)

    ordered = sorted(sites, key=lambda key: (key[0], int(key[1]), key[2], key[3]))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as handle:
        handle.write("##fileformat=VCFv4.2\n")
        handle.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n')
        handle.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT")
        for sample in SAMPLES:
            handle.write(f"\t{sample}")
        handle.write("\n")
        for key in ordered:
            chrom, pos, ref, alt = key
            ident = ids.get(key, ".")
            values = [sites[key].get(sample, "./.") for sample in SAMPLES]
            handle.write(
                f"{chrom}\t{pos}\t{ident}\t{ref}\t{alt}\t.\t.\t.\tGT\t"
                + "\t".join(values)
                + "\n"
            )
    print(f"wrote {len(ordered)} ALT rows to {out}")


if __name__ == "__main__":
    main()
