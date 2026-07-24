"""The portable provenance bundle (ARCHITECTURE §7).

A bundle is the artifact that makes a run "re-runnable by a stranger": the full
RunRecord serialized to disk, plus the helper that derives the input checksums
that anchor it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from contig.models import (
    AnnotationProvenance,
    ReferenceIdentity,
    ReproduceRecord,
    RunRecord,
    SexInference,
    sha256_file,
)
from contig.verification.annotation_structural import _open_text
from contig.verification.sex_plausibility import sex_signals
from contig.verification.structural import manifest_for

# The env var that, when set to a hex or base64 Ed25519 private key, makes
# write_bundle emit a detached signature sidecar next to the record. Absent or
# empty means no sidecar (signing is opt-in and never logs the key).
SIGNING_KEY_ENV = "CONTIG_SIGNING_KEY"


def write_bundle(record: RunRecord, dest_dir: str | Path) -> Path:
    """Serialize ``record`` to ``dest_dir/run_record.json`` and return that path.

    When ``CONTIG_SIGNING_KEY`` is set (and signing is available), also write a
    detached signature sidecar at ``dest_dir/signature.json`` over the record's
    canonical content. The signature signs the record content, never the sidecar.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / "run_record.json"
    json_path.write_text(record.model_dump_json(indent=2))
    _maybe_write_signature(record, dest)
    return json_path


def _maybe_write_signature(record: RunRecord, dest: Path) -> None:
    """Write signature.json when a signing key is configured; otherwise do nothing."""
    private_key = os.environ.get(SIGNING_KEY_ENV)
    if not private_key:
        return
    # Imported lazily so the bundle module loads even where cryptography is absent;
    # a configured key with signing unavailable raises, surfacing the misconfig.
    from contig.signing import canonical_sha256, public_key_for, sign_record

    sidecar = {
        "algo": "ed25519",
        "public_key": public_key_for(private_key),
        "signature": sign_record(record, private_key),
        "signed_sha256": canonical_sha256(record),
    }
    (dest / "signature.json").write_text(json.dumps(sidecar, indent=2))


def load_bundle(dest_dir: str | Path) -> RunRecord:
    """Reconstruct the RunRecord from ``dest_dir/run_record.json``."""
    json_path = Path(dest_dir) / "run_record.json"
    return RunRecord.model_validate_json(json_path.read_text())


def write_reproduce_bundle(
    record: ReproduceRecord, dest_dir: str | Path, *, requested_rev: str | None = None
) -> Path:
    """Serialize ``record`` to ``dest_dir/reproduce_record.json`` and return that path.

    Also writes ``dest_dir/reproduce.json``, the small re-runnable manifest (repo +
    run_command + claims_sha256 + source_url + source_commit, no absolute scratch
    paths -- mirrors LaunchManifest's discipline of omitting scratch/outdir paths;
    for a remote run ``repo`` holds the URL and the local checkout path is never
    persisted). ``source_url``/``source_commit`` are emitted unconditionally --
    present and ``null`` for a local run -- so a consumer can always read the key
    without a ``.get()`` dance. ``requested_rev`` -- the ``--rev`` the caller asked
    for, which for a tag or branch is not recoverable from the resolved SHA -- is
    emitted the same way. It lives in the manifest and NOT on the record
    deliberately: the manifest is unsigned invocation metadata, so adding it breaks
    no existing signature, and the resolved ``source_commit`` stays the attested
    fact. When ``CONTIG_SIGNING_KEY`` is set,
    also writes a detached signature sidecar over the record's canonical content, via
    the same ``_maybe_write_signature`` used for RunRecord -- it only calls
    ``record.model_dump(mode="json")`` under the hood, so it signs a ReproduceRecord
    exactly as it signs a RunRecord.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / "reproduce_record.json"
    json_path.write_text(record.model_dump_json(indent=2))
    _maybe_write_signature(record, dest)

    manifest = {
        "reproduce_id": record.reproduce_id,
        "repo": record.repo,
        "run_command": record.run_command,
        "claims_sha256": record.claims_sha256,
        "created_at": record.created_at,
        "source_url": record.source_url,
        "source_commit": record.source_commit,
        "requested_rev": requested_rev,
    }
    (dest / "reproduce.json").write_text(json.dumps(manifest, indent=2))

    return json_path


def load_reproduction(dir: str | Path) -> ReproduceRecord:
    """Reconstruct the ReproduceRecord from ``dir/reproduce_record.json``.

    Raises ``FileNotFoundError`` with a clear message when the file is absent
    (mirrors workspace.load_run's discipline of failing clearly on a missing bundle).
    """
    json_path = Path(dir) / "reproduce_record.json"
    if not json_path.is_file():
        raise FileNotFoundError(f"no reproduce record at {json_path}")
    return ReproduceRecord.model_validate_json(json_path.read_text())


def compute_input_checksums(paths: list[str | Path]) -> dict[str, str]:
    """Map each input file's basename to its SHA-256, for RunRecord.input_checksums.

    Basenames keep the provenance portable, but two inputs sharing a basename would
    silently clobber (corrupting the record), so a collision is a hard error.
    """
    checksums: dict[str, str] = {}
    for p in paths:
        name = Path(p).name
        if name in checksums:
            raise ValueError(f"duplicate input basename {name!r}; inputs must have unique names")
        checksums[name] = sha256_file(p)
    return checksums


def compute_reference_identity(
    params: dict[str, object] | None,
) -> ReferenceIdentity | None:
    """Derive reference identity from a run's parameters.

    Explicit mode (--fasta/--gtf): record the paths and their sha256. iGenomes mode
    (--genome KEY): record the key only — the pipeline downloads the files, so Contig
    has no local path to hash. No reference keys → None (e.g. Snakemake runs).
    A missing/unreadable local reference degrades to a None checksum, never a crash
    and never a fabricated hash.
    """
    if not params:
        return None
    genome = params.get("genome")
    fasta = params.get("fasta")
    gtf = params.get("gtf")
    if genome:
        return ReferenceIdentity(mode="igenomes", genome=str(genome))
    if not fasta and not gtf:
        return None

    def _hash(p):
        try:
            return sha256_file(p) if p and Path(p).is_file() else None
        except OSError:
            return None

    return ReferenceIdentity(
        mode="explicit",
        fasta=str(fasta) if fasta else None,
        gtf=str(gtf) if gtf else None,
        fasta_sha256=_hash(fasta),
        gtf_sha256=_hash(gtf),
    )


_CACHE_TOKEN_RE = re.compile(r'cache="([^"]*)"')
# An assembly/genome DB token like "GRCh38.105" -- letters/digits then a dot-number.
_SNPEFF_GENOME_RE = re.compile(r"\b([A-Za-z0-9]+\.\d[\w.]*)\b")


def _extract_vep_cache(line: str) -> str | None:
    """Return the basename of a VEP ``cache="..."`` token, or None if absent.

    ``/vep/homo_sapiens/110_GRCh38`` -> ``110_GRCh38``. Handles a trailing slash
    and a ``file://`` prefix. Never fabricates: no token / empty token -> None.
    """
    match = _CACHE_TOKEN_RE.search(line)
    if not match:
        return None
    path = match.group(1).strip()
    if path.startswith("file://"):
        path = path[len("file://"):]
    path = path.rstrip("/")
    if not path:
        return None
    return os.path.basename(path) or None


def _extract_snpeff_db(header_lines: list[str]) -> str | None:
    """Scan SnpEff header lines for the genome DB token (e.g. ``GRCh38.105``), or None.

    Real SnpEff output writes the genome DB ONLY on the ``##SnpEffCmd`` line, as the
    first positional token right after ``SnpEff␣␣`` (double space), with annotation
    flags following it, e.g.
    ``##SnpEffCmd="SnpEff  GRCh38.105 -csvStats test.csv input.vcf "``. There is no
    ``##SnpEffGenomeVersion`` header -- SnpEff emits only ``##SnpEffVersion`` and
    ``##SnpEffCmd``. Never fabricates: no ``##SnpEffCmd`` (or no DB token on it) -> None.
    """
    for line in header_lines:
        if line.startswith("##SnpEffCmd="):
            match = _SNPEFF_GENOME_RE.search(line)
            if match:
                return match.group(1)
    return None


def _parse_annotation_header(header_lines: list[str]) -> "AnnotationProvenance | None":
    """Parse VEP/SnpEff tool + version (+ cache/build db_version) from VCF header lines.

    VEP is a single-line parse (tool, version, cache token on the ``##VEP=`` line).
    SnpEff needs to scan the whole header block: the version is on ``##SnpEffVersion=``
    but the genome DB token lives on the separate ``##SnpEffCmd=`` line, so it does not
    early-return on the version line.
    """
    for line in header_lines:
        if line.startswith("##VEP="):
            # ##VEP="v110" time="..." cache="..."
            value = line[len("##VEP="):].strip()
            version = value.split()[0].strip('"') if value else None
            return AnnotationProvenance(
                tool="VEP",
                version=version,
                db_version=_extract_vep_cache(line),
                raw_header=line.strip(),
            )
    for line in header_lines:
        if line.startswith("##SnpEffVersion="):
            value = line[len("##SnpEffVersion="):].strip().strip('"')
            return AnnotationProvenance(
                tool="SnpEff",
                version=value or None,
                db_version=_extract_snpeff_db(header_lines),
                raw_header=line.strip(),
            )
    return None


def compute_annotation_identity(run_dir: Path) -> list["AnnotationProvenance"]:
    """Locate annotated VCFs under run_dir and parse ALL annotation provenances.

    M4 enables both VEP and SnpEff on the variant assays, so a run can carry
    two distinct annotators. Globs `**/*.vcf.gz`, reads only each file's header
    (up to `#CHROM`), and returns every distinct provenance found, deduped by
    tool (first occurrence wins per tool) in deterministic order (sorted by
    tool name). Empty list when no annotated VCF exists — never a fabricated
    tool/version. Reproduce-safe: derived from the output VCFs, not a stored
    scratch path.
    """
    found: dict[str, AnnotationProvenance] = {}
    for vcf in sorted(Path(run_dir).glob("**/*.vcf.gz")):
        header_lines: list[str] = []
        with _open_text(vcf) as fh:
            for line in fh:
                if not line.startswith("#"):
                    break
                header_lines.append(line)
                if line.startswith("#CHROM"):
                    break
        prov = _parse_annotation_header(header_lines)
        if prov is not None and prov.tool not in found:
            found[prov.tool] = prov
    return [found[tool] for tool in sorted(found)]


def compute_sex_inference(run_dir: Path) -> "SexInference | None":
    """Derive germline karyotypic-sex provenance from the run's primary VCF.

    Locates the germline VCF EXACTLY as runner._discover_qc does (the
    variant_calling manifest's first required glob, rglob'd under run_dir,
    taking vcfs[0]) so provenance and the verdict describe the same call set --
    a divergent second discovery path would be a real bug, not a style choice.
    No VCF -> None (never fabricated). The actual inference is
    verification.sex_plausibility.sex_signals; this just maps it to the
    serializable provenance model.
    """
    pattern = manifest_for("variant_calling").required[0]  # "*.vcf.gz"
    vcfs = sorted(p for p in Path(run_dir).rglob(pattern) if p.is_file())
    if not vcfs:
        return None
    signals = sex_signals(vcfs[0])
    return SexInference(
        inferred_sex=signals.inferred_sex,
        x_het_ratio=signals.x_het_ratio,
        x_sites=signals.x_sites,
        y_variant_count=signals.y_variant_count,
        par_masked=signals.par_masked,
        reference_build=signals.reference_build,
    )


def compute_output_checksums(results_dir: str | Path) -> dict[str, str]:
    """Map each output file under ``results_dir`` to its SHA-256 (PRD contract B).

    Keys are paths relative to ``results_dir`` (POSIX separators, so the key
    survives a re-hash on any platform); this anchors the produced outputs in the
    RunRecord so ``contig verify`` can detect drift. An absent results dir maps to
    an empty dict: a run that produced no outputs has nothing to anchor.
    """
    root = Path(results_dir)
    if not root.is_dir():
        return {}
    checksums: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        checksums[rel] = sha256_file(path)
    return checksums


def compute_tree_sha256(root: str | Path) -> str | None:
    """Deterministic, stdlib-only digest of a checkout tree (C8 slice 8).

    Walks ``root`` with ``os.walk(followlinks=False)``, pruning any directory
    component named ``.git`` (at any depth) and any symlinked directory, so
    the digest never crosses a repo boundary or leaves containment. For each
    regular non-symlink file, folds ``f"{posix_relpath}\\0{sha256_file(path)}\\n"``
    (NUL delimiter -- illegal in POSIX paths) into a sorted list, then returns
    the hex SHA-256 of the UTF-8 concatenation. This exact algorithm is
    published (CHANGELOG) so a third party can recompute it byte-for-byte.

    Honest degradation: a missing or non-directory root, or any ``OSError``
    while reading a file, returns ``None`` -- never a partial or fabricated
    digest.
    """
    base = Path(root)
    if not base.is_dir():
        return None
    lines: list[str] = []
    try:
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            # Prune .git dirs and symlinked dirs in place (os.walk honors edits).
            dirnames[:] = [
                d for d in dirnames if d != ".git" and not Path(dirpath, d).is_symlink()
            ]
            for name in filenames:
                p = Path(dirpath, name)
                if p.is_symlink() or not p.is_file():
                    continue
                rel = p.relative_to(base).as_posix()
                lines.append(f"{rel}\0{sha256_file(p)}\n")
    except OSError:
        return None
    blob = "".join(sorted(lines)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
