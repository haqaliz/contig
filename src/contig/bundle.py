"""The portable provenance bundle (ARCHITECTURE §7).

A bundle is the artifact that makes a run "re-runnable by a stranger": the full
RunRecord serialized to disk, plus the helper that derives the input checksums
that anchor it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from contig.models import ReferenceIdentity, RunRecord, sha256_file

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


def compute_reference_identity(params):
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
