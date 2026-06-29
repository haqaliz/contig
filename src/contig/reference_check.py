"""Pre-flight reference-consistency check (FASTA vs GTF contig naming).

Catch a FASTA/GTF pair whose contig-naming schemes are DISJOINT (e.g. the FASTA
uses ``chr1`` while the GTF uses ``1``) before an nf-core run launches and
silently produces an empty count matrix. Local, deterministic, no network.
"""

import gzip
from pathlib import Path


def _open_text(path):
    p = Path(path)
    return gzip.open(p, "rt") if p.name.endswith(".gz") else open(p)


def fasta_contigs(path) -> set[str]:
    names: set[str] = set()
    with _open_text(path) as fh:
        for line in fh:
            if line.startswith(">"):
                token = line[1:].split()
                if token:
                    names.add(token[0])
    return names


def gtf_contigs(path) -> set[str]:
    names: set[str] = set()
    with _open_text(path) as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            field0 = line.split("\t", 1)[0].strip()
            if field0:
                names.add(field0)
    return names


def _sample(names: set[str], n: int = 3) -> str:
    return ", ".join(sorted(names)[:n])


def _all_chr_prefixed(names: set[str]) -> bool:
    return bool(names) and all(n.startswith("chr") for n in names)


def check_reference_consistency(fasta_path, gtf_path) -> list[str]:
    fasta = fasta_contigs(fasta_path)
    gtf = gtf_contigs(gtf_path)
    if not fasta or not gtf:          # uncomparable -> never a false refuse
        return []
    if fasta & gtf:                   # any shared contig -> OK
        return []
    msg = (
        "reference FASTA and GTF use incompatible contig naming "
        f"(no shared contig): FASTA has [{_sample(fasta)}], "
        f"GTF has [{_sample(gtf)}]"
    )
    if _all_chr_prefixed(fasta) and not _all_chr_prefixed(gtf):
        msg += "; FASTA uses 'chr'-prefixed names but the GTF does not"
    elif _all_chr_prefixed(gtf) and not _all_chr_prefixed(fasta):
        msg += "; the GTF uses 'chr'-prefixed names but the FASTA does not"
    return [msg]
