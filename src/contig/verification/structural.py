"""Structural/integrity QC checks on a run's output files (ARCHITECTURE §6.1).

These are the cheapest verification layer: does the output exist, is it non-empty,
is it indexed, is a gzip stream intact, does a BAM carry its terminator. They run
before any content-level QC, since a missing or truncated file makes deeper checks
meaningless. Every result carries kind "structural" so the dashboard can group
them apart from the metric checks.

Nothing here executes an output: integrity is judged by reading bytes (gzip magic,
a full decompress, the BGZF EOF block), never by running a tool over the file.
"""

from __future__ import annotations

import gzip
import os
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field

from contig.models import QCResult


def _structural(check: str, status: str, message: str, value: float | None = None) -> QCResult:
    """Build a QCResult tagged as structural so the dashboard groups it correctly."""
    return QCResult(check=check, status=status, message=message, value=value, kind="structural")


def check_output(path: str | os.PathLike) -> QCResult:
    """`fail` if the path is missing or zero bytes, else `pass`; value is byte size."""
    p = Path(path)
    if not p.is_file():
        return _structural(
            f"output_present:{p.name}",
            "fail",
            "output is missing",
        )
    size = p.stat().st_size
    if size == 0:
        return _structural(
            f"output_present:{p.name}",
            "fail",
            "output is empty (0 bytes)",
            value=0.0,
        )
    return _structural(
        f"output_present:{p.name}",
        "pass",
        "output present and non-empty",
        value=float(size),
    )


def check_index_present(alignment_path: str | os.PathLike) -> QCResult:
    """`pass` if a sibling index (`.bai` or `.csi`) exists, else `fail`."""
    p = Path(alignment_path)
    has_index = any(
        p.with_name(p.name + suffix).is_file() for suffix in (".bai", ".csi")
    )
    if has_index:
        return _structural(
            f"index_present:{p.name}",
            "pass",
            "alignment index present",
        )
    return _structural(
        f"index_present:{p.name}",
        "fail",
        "alignment index missing (.bai/.csi)",
    )


_GZIP_MAGIC = b"\x1f\x8b"

# The 28 byte empty-block marker every BGZF stream (and thus every well-formed BAM)
# ends with. samtools writes it as the final bytes so readers can confirm the file
# was not truncated. We compare the file's tail against it; we do not run samtools.
_BGZF_EOF = bytes.fromhex(
    "1f8b08040000000000ff0600424302001b0003000000000000000000"
)


def check_gzip_ok(path: str | os.PathLike) -> QCResult:
    """`pass` if the file exists, is non-empty, and starts with gzip magic bytes."""
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return _structural(
            f"gzip_ok:{p.name}",
            "fail",
            "output is missing or empty",
        )
    with open(p, "rb") as fh:
        header = fh.read(2)
    if header == _GZIP_MAGIC:
        return _structural(
            f"gzip_ok:{p.name}",
            "pass",
            "gzip magic bytes present",
        )
    return _structural(
        f"gzip_ok:{p.name}",
        "fail",
        "missing gzip magic bytes (truncated or not gzip)",
    )


def check_gzip_integrity(path: str | os.PathLike) -> QCResult:
    """`pass` only if the whole gzip stream decompresses (CRC and length verify).

    Stronger than the magic-byte check: a truncated `.gz` keeps its header but
    fails to decompress, which is exactly the corruption we want to catch. We
    stream the decompression so a large output never loads into memory.
    """
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return _structural(
            f"gzip_integrity:{p.name}",
            "fail",
            "output is missing or empty",
        )
    try:
        with gzip.open(p, "rb") as fh:
            while fh.read(1 << 20):
                pass
    except (OSError, EOFError) as exc:
        return _structural(
            f"gzip_integrity:{p.name}",
            "fail",
            f"gzip stream did not decompress (truncated or corrupt): {exc}",
        )
    return _structural(
        f"gzip_integrity:{p.name}",
        "pass",
        "gzip stream decompressed cleanly",
    )


def check_bam_ok(path: str | os.PathLike) -> QCResult:
    """`pass` if a BAM is a valid BGZF stream that ends with the BGZF EOF block.

    BAM is BGZF (block-gzipped). A truncated BAM is the classic silent corruption:
    samtools writes a fixed 28 byte empty block at the end, and a file missing it
    was cut short. We confirm the gzip magic, that the stream decompresses, and
    that the trailing bytes are the EOF marker, all without running samtools.
    """
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return _structural(
            f"bam_ok:{p.name}",
            "fail",
            "BAM is missing or empty",
        )
    with open(p, "rb") as fh:
        if fh.read(2) != _GZIP_MAGIC:
            return _structural(
                f"bam_ok:{p.name}",
                "fail",
                "not a gzip/BGZF stream (BAM header missing)",
            )
    try:
        with gzip.open(p, "rb") as fh:
            while fh.read(1 << 20):
                pass
    except (OSError, EOFError) as exc:
        return _structural(
            f"bam_ok:{p.name}",
            "fail",
            f"BAM stream did not decompress (truncated or corrupt): {exc}",
        )
    eof_len = len(_BGZF_EOF)
    with open(p, "rb") as fh:
        if p.stat().st_size >= eof_len:
            fh.seek(-eof_len, os.SEEK_END)
        tail = fh.read()
    if tail.endswith(_BGZF_EOF):
        return _structural(
            f"bam_ok:{p.name}",
            "pass",
            "BAM decompressed and carries the BGZF EOF marker",
        )
    return _structural(
        f"bam_ok:{p.name}",
        "fail",
        "BAM is missing its BGZF EOF marker (truncated)",
    )


def check_output_count(
    results_dir: str | os.PathLike, pattern: str, expected: int
) -> QCResult:
    """`fail` if fewer files than `expected` match `pattern` under `results_dir`.

    Catches the run that silently produced outputs for only some samples. More
    than expected is a `warn` (extra files are odd but not a missing-output
    failure); an exact match passes.
    """
    root = Path(results_dir)
    found = len(list(root.rglob(pattern)))
    if found < expected:
        status = "fail"
        message = f"expected {expected} {pattern} output(s), found {found}"
    elif found > expected:
        status = "warn"
        message = f"expected {expected} {pattern} output(s), found {found} (more than expected)"
    else:
        status = "pass"
        message = f"found the expected {expected} {pattern} output(s)"
    return _structural(
        f"output_count:{pattern}",
        status,
        message,
        value=float(found),
    )


class ExpectedOutputs(BaseModel):
    """A per-assay manifest of which outputs a finished run must produce.

    Drives the structural checks declaratively (data, not code), so a new assay
    adds a manifest entry rather than new check logic. Patterns are glob patterns
    matched recursively under the run's results directory.

    - `required`: a missing or empty match FAILs the verdict.
    - `optional`: a missing match is a soft WARN, never a fail.
    - `indexed`: each match must have a sibling `.bai`/`.csi` (FAIL if not).
    - `bam`: each match is checked for BAM/BGZF integrity (FAIL on corruption).
    - `gzip`: each match is checked for gzip-stream integrity (FAIL on corruption).
    - `counts`: pattern -> expected file count, for per-sample completeness.
    """

    required: list[str] = Field(default_factory=list)
    optional: list[str] = Field(default_factory=list)
    indexed: list[str] = Field(default_factory=list)
    bam: list[str] = Field(default_factory=list)
    gzip: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


# Per-assay manifests: which outputs each curated pipeline must produce. Patterns
# track the documented nf-core output layout for each assay; they are conservative
# (the headline result file), so a real run that produced it passes and a run that
# silently produced nothing fails. New assays add an entry, not new check code.
_ASSAY_MANIFESTS: dict[str, ExpectedOutputs] = {
    "rnaseq": ExpectedOutputs(
        required=["*.bam", "*salmon.merged.gene_counts*"],
        optional=["*.cram"],
        bam=["*.bam"],
    ),
    "variant_calling": ExpectedOutputs(
        required=["*.vcf.gz"],
        gzip=["*.vcf.gz"],
    ),
    # Somatic sarek outputs land under variant_calling/<caller>/<tumor>_vs_<normal>/.
    # Deliberately minimal and mirroring germline: require an intact bgzipped VCF.
    # No `indexed` — somatic VCFs ship a `.tbi`, which check_index_present does not
    # recognize (only .bai/.csi), so asserting it would false-fail an intact run.
    "somatic_variant_calling": ExpectedOutputs(
        required=["*.vcf.gz"],
        gzip=["*.vcf.gz"],
    ),
    "scrnaseq": ExpectedOutputs(
        required=["*.h5ad", "*matrix.mtx*"],
    ),
    "methylseq": ExpectedOutputs(
        required=["*.bam", "*.bedGraph.gz"],
        bam=["*.bam"],
        gzip=["*.bedGraph.gz"],
    ),
    "ampliseq": ExpectedOutputs(
        required=["*ASV_table*", "*.fasta*"],
    ),
    "mag": ExpectedOutputs(
        required=["*.fa*"],
    ),
}


def manifest_for(assay: str) -> ExpectedOutputs:
    """Select the expected-output manifest for an assay; unknown assays are a hard error."""
    try:
        return _ASSAY_MANIFESTS[assay]
    except KeyError:
        raise ValueError(f"no expected-output manifest for assay {assay!r}") from None


def _glob(results_dir: Path, pattern: str) -> list[Path]:
    return sorted(p for p in results_dir.rglob(pattern) if p.is_file())


def evaluate_against_manifest(
    results_dir: str | os.PathLike, manifest: ExpectedOutputs
) -> list[QCResult]:
    """Apply a per-assay manifest to a run's outputs, emitting structural results.

    A required pattern that matches nothing FAILs (the output is missing); each
    match is then checked for presence/non-emptiness. Optional patterns that match
    nothing WARN. Indexed/bam/gzip patterns add the corresponding integrity check
    per match. Counts add a per-pattern completeness check.
    """
    root = Path(results_dir)
    results: list[QCResult] = []

    for pattern in manifest.required:
        matches = _glob(root, pattern)
        if not matches:
            results.append(
                _structural(
                    f"output_present:{pattern}",
                    "fail",
                    f"required output {pattern} is missing (no file matched)",
                )
            )
            continue
        results.extend(check_output(m) for m in matches)

    for pattern in manifest.optional:
        matches = _glob(root, pattern)
        if not matches:
            results.append(
                _structural(
                    f"output_present:{pattern}",
                    "warn",
                    f"optional output {pattern} is absent",
                )
            )
            continue
        results.extend(check_output(m) for m in matches)

    for pattern in manifest.indexed:
        for m in _glob(root, pattern):
            results.append(check_index_present(m))

    for pattern in manifest.bam:
        for m in _glob(root, pattern):
            results.append(check_bam_ok(m))

    for pattern in manifest.gzip:
        for m in _glob(root, pattern):
            results.append(check_gzip_integrity(m))

    for pattern, expected in manifest.counts.items():
        results.append(check_output_count(root, pattern, expected))

    return results


def evaluate_structural(
    paths: Sequence[str | os.PathLike],
    index_for: Sequence[str | os.PathLike] = (),
) -> list[QCResult]:
    """Run `check_output` on every path and `check_index_present` on `index_for`."""
    results = [check_output(p) for p in paths]
    results.extend(check_index_present(p) for p in index_for)
    return results
