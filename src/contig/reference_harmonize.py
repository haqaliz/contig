"""Pure decision + stream-rewriter for GTF contig-name harmonization.

This module provides two public functions:

- ``plan_harmonization(fasta_path, gtf_path)`` — pure decision: builds a
  FASTA-driven rename map for the GTF's seqnames (chr-prefix AND alias-table
  aware — mitochondrion ``chrM``/``MT``, scaffolds) and returns a
  ``HarmonizationPlan`` only when applying it would strictly improve the
  FASTA/GTF contig-name overlap; ``None`` otherwise.

- ``harmonize_gtf(gtf_path, rename_map, out_path)`` — stream-rewrites the GTF
  applying *rename_map* to column 1 only; a seqname absent from the map
  passes through unchanged; byte-faithful everywhere else; gzip-transparent.

No network, no subprocess, no mutations of input files.
"""

import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from contig.contig_aliases import alias_group
from contig.reference_check import _sample, fasta_contigs, gtf_contigs


@dataclass(frozen=True)
class HarmonizationPlan:
    rename_map: dict[str, str]  # GTF seqname -> FASTA seqname, renames only
    direction: str              # "add_chr" | "strip_chr" | "alias"
    unmatched: tuple[str, ...]  # GTF seqnames with no FASTA candidate at all
    fasta_sample: str           # _sample(fasta_contigs) — for user-facing notes
    gtf_sample: str             # _sample(gtf_contigs)   — for user-facing notes


def _prefix_variants(name: str) -> set[str]:
    """All chr-prefix spellings of *name*: itself, ``chr``-prefixed, and (if
    *name* is already ``chr``-prefixed and long enough) the bare/stripped form.
    """
    variants = {name, f"chr{name}"}
    if name.startswith("chr") and len(name) > 3:
        variants.add(name[3:])
    variants.discard("")
    return variants


def _candidate_names(g: str) -> set[str]:
    """All FASTA-side spellings *g* could plausibly rename to.

    Unifies prefix handling and alias-table lookup: expand *g* through its
    own prefix variants first (so a chr-prefixed spelling like ``chrMT``
    reaches the bare-name alias table entry ``MT`` <-> ``M``), look up the
    alias group of every one of those variants, then expand each alias
    through prefix variants again (so the alias's own chr-prefixed form,
    e.g. ``chrM``, is reachable too). This is what lets a hybrid FASTA
    (``chrMT``) resolve a bare GTF (``MT``) and a UCSC FASTA (``chrM``)
    resolve the same bare GTF (``MT``) — the FASTA's actual spelling wins
    either way once intersected with F in the caller.
    """
    names: set[str] = set()
    for v in _prefix_variants(g):
        for a in alias_group(v):
            names |= _prefix_variants(a)
    return names


def plan_harmonization(fasta_path, gtf_path) -> HarmonizationPlan | None:
    """Build a FASTA-driven rename map for the GTF and decide whether to apply it.

    For every GTF seqname, compute the candidate FASTA spellings via
    ``_candidate_names`` (prefix + alias union), intersected against the
    actual FASTA contig set. Refuses (returns ``None``) unless applying the
    resulting rename map would strictly increase the FASTA/GTF name overlap.
    """
    # Step 1: parse both sides; either side unparseable -> uncomparable.
    fa = fasta_contigs(fasta_path)
    gt = gtf_contigs(gtf_path)
    if not fa or not gt:
        return None

    # Step 2/3: for each GTF seqname, resolve against the FASTA set.
    rename_map: dict[str, str] = {}
    unmatched: list[str] = []
    for g in gt:
        cands = _candidate_names(g) & fa
        if not cands:
            unmatched.append(g)
            continue
        chosen = g if g in fa else sorted(cands)[0]
        if chosen != g:
            rename_map[g] = chosen

    # Step 4: overlap before vs. after applying the rename map. Keep the
    # post-harmonization names as a list (not just a set) so a collision
    # between two distinct GTF seqnames is still visible for the
    # injectivity check below.
    overlap_before = len(fa & gt)
    mapped_list = [rename_map.get(g, g) for g in gt]
    mapped = set(mapped_list)
    overlap_after = len(fa & mapped)

    # Step 5: refuse / no-op — nothing resolvable, already consistent,
    # a strict subset, or a genuine wrong-assembly mismatch renaming can't fix.
    if not rename_map or overlap_after <= overlap_before:
        return None

    # Step 6: explicit disjoint guard (redundant with step 5, kept explicit
    # per spec) — a wrong-assembly pair must never be "resolved".
    if not (fa & mapped):
        return None

    # Step 6b: injectivity guard — refuse if the rename map is not injective.
    # Two distinct GTF seqnames must never land on the same post-harmonization
    # name, whether both get renamed onto a shared target (e.g. GTF {M, MT}
    # both resolving to FASTA chrM) or one gets renamed onto a name another
    # seqname already has unchanged. Applying such a map would silently merge
    # two distinct contigs into one downstream; refuse rather than corrupt
    # the data.
    if len(mapped_list) != len(mapped):
        return None

    # Step 7: derive the direction label. Preserve the legacy "add_chr" /
    # "strip_chr" labels when every rename follows that single uniform
    # pattern exactly (this is what the pre-Phase-2 callers/tests assert);
    # anything else (mixed prefix+alias, or pure alias) is labeled "alias".
    if all(v == f"chr{k}" for k, v in rename_map.items()):
        direction = "add_chr"
    elif all(v == k[3:] for k, v in rename_map.items()):
        direction = "strip_chr"
    else:
        direction = "alias"

    return HarmonizationPlan(
        rename_map=rename_map,
        direction=direction,
        unmatched=tuple(sorted(unmatched)),
        fasta_sample=_sample(fa),
        gtf_sample=_sample(gt),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _open_input(path: Path):
    """Open path for reading; gzip-aware iff the filename ends with .gz."""
    return gzip.open(path, "rt") if path.name.endswith(".gz") else open(path, "r", newline="")


def _open_output(path: Path):
    """Open path for writing; gzip-aware iff the filename ends with .gz."""
    if path.name.endswith(".gz"):
        return gzip.open(path, "wt")
    return open(path, "w", newline="")


# ---------------------------------------------------------------------------
# Public rewriter
# ---------------------------------------------------------------------------

def harmonize_gtf(gtf_path, rename_map: Mapping[str, str], out_path) -> Path:
    """Stream-rewrite *gtf_path* applying *rename_map* to column 1 only.

    - Blank lines and lines starting with ``#`` are passed through unchanged.
    - ``track`` / ``browser`` lines (no tab-delimited seqname) are passed
      through unchanged.
    - Column 1 is tokenized with the same boundary as ``gtf_contigs``
      (``split("\\t", 1)``); the (stripped) token is looked up in
      *rename_map* and rewritten; a seqname absent from the map passes
      through unchanged.
    - Everything after the first tab is byte-identical in the output.
    - Line endings (``\\n`` vs ``\\r\\n``) are preserved exactly.
    - Input/output are gzip-compressed iff the respective path ends with ``.gz``.

    Returns *out_path* as a :class:`~pathlib.Path`.
    """
    gtf_path = Path(gtf_path)
    out_path = Path(out_path)

    with _open_input(gtf_path) as fh_in, _open_output(out_path) as fh_out:
        for raw_line in fh_in:
            # Detect line ending without stripping the whole line.
            if raw_line.endswith("\r\n"):
                ending = "\r\n"
                line = raw_line[:-2]
            elif raw_line.endswith("\n"):
                ending = "\n"
                line = raw_line[:-1]
            else:
                # Last line with no trailing newline.
                ending = ""
                line = raw_line

            # Pass through blanks and comment/pragma lines unchanged.
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                fh_out.write(raw_line)
                continue

            # Split on the first tab to isolate column 1.
            if "\t" not in line:
                # No tab → not a standard GTF data line (e.g. track/browser).
                fh_out.write(raw_line)
                continue

            col1, rest = line.split("\t", 1)
            # Strip the token to match the boundary that gtf_contigs uses
            # (.strip() on field0), so a malformed GTF with leading/trailing
            # whitespace on the seqname is transformed consistently with what
            # the detector sees.  Columns 2+ (rest) remain byte-identical.
            stripped_col1 = col1.strip()
            new_col1 = rename_map.get(stripped_col1, stripped_col1)
            fh_out.write(new_col1 + "\t" + rest + ending)

    return out_path
