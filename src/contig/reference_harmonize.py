"""Pure decision + stream-rewriter for GTF contig-name harmonization.

This module provides two public functions:

- ``plan_harmonization(fasta_path, gtf_path)`` — pure decision: returns a
  ``HarmonizationPlan`` only when a safe uniform ``chr``-prefix transform on
  the GTF will resolve a detected FASTA/GTF naming mismatch; ``None`` otherwise.

- ``harmonize_gtf(gtf_path, direction, out_path)`` — stream-rewrites the GTF
  applying the direction to column 1 only; byte-faithful everywhere else;
  gzip-transparent.

No network, no subprocess, no mutations of input files.
"""

import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from contig.reference_check import (
    _all_chr_prefixed,
    _sample,
    check_reference_consistency,
    fasta_contigs,
    gtf_contigs,
)

HarmonizationDirection = Literal["add_chr", "strip_chr"]


@dataclass(frozen=True)
class HarmonizationPlan:
    direction: HarmonizationDirection
    fasta_sample: str   # _sample(fasta_contigs) — for user-facing notes
    gtf_sample: str     # _sample(gtf_contigs)   — for user-facing notes


def plan_harmonization(fasta_path, gtf_path) -> HarmonizationPlan | None:
    """Decide whether a safe uniform chr-prefix transform resolves the mismatch.

    Returns a :class:`HarmonizationPlan` only when:
    - ``check_reference_consistency`` reports a mismatch (non-empty), AND
    - the mismatch is an unambiguous chr-prefix asymmetry (one side all-chr,
      the other none-chr), AND
    - after applying the transform the two sets share at least one name.

    Returns ``None`` in all other cases so the caller can refuse safely.
    """
    # Step 1: only act when there is an actual mismatch.
    if not check_reference_consistency(fasta_path, gtf_path):
        return None

    # Step 2: parse both sides.
    fa = fasta_contigs(fasta_path)
    gt = gtf_contigs(gtf_path)

    # Step 3: determine direction.
    if _all_chr_prefixed(fa) and not _all_chr_prefixed(gt):
        direction: HarmonizationDirection = "add_chr"
        transformed = {f"chr{n}" for n in gt}
    elif _all_chr_prefixed(gt) and not _all_chr_prefixed(fa):
        direction = "strip_chr"
        transformed = {n[3:] if n.startswith("chr") else n for n in gt}
    else:
        # Mixed prefixes or both bare-vs-bare: not an unambiguous asymmetry.
        return None

    # Step 4: post-transform must intersect FASTA — otherwise it's a genuine
    # wrong-assembly, not a prefix convention difference.
    if not (transformed & fa):
        return None

    # Step 5: safe — return the plan.
    return HarmonizationPlan(
        direction=direction,
        fasta_sample=_sample(fa),
        gtf_sample=_sample(gt),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply(name: str, direction: HarmonizationDirection) -> str:
    """Apply the direction to a single seqname; idempotent."""
    if direction == "add_chr":
        return name if name.startswith("chr") else f"chr{name}"
    else:  # strip_chr
        return name[3:] if name.startswith("chr") else name


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

def harmonize_gtf(gtf_path, direction: HarmonizationDirection, out_path) -> Path:
    """Stream-rewrite *gtf_path* applying *direction* to column 1 only.

    - Blank lines and lines starting with ``#`` are passed through unchanged.
    - ``track`` / ``browser`` lines (no tab-delimited seqname) are passed
      through unchanged.
    - Column 1 is tokenized with the same boundary as ``gtf_contigs``
      (``split("\\t", 1)``); the token is transformed and re-joined.
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
            new_col1 = _apply(col1, direction)
            fh_out.write(new_col1 + "\t" + rest + ending)

    return out_path
