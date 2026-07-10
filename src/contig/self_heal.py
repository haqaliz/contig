"""The self-healing loop: Contig's core IP (ARCHITECTURE §5).

Wrap a run in a bounded, observable, fully-logged control loop:

    EXECUTE → DETECT → DIAGNOSE → PROPOSE → (apply safe patch) → re-run

Every detect→diagnose→patch→outcome transition is persisted to the RunRecord's
`repair_history`, so the repair chain is provenance. Only `safe` patches
auto-apply; `needs_confirmation`/`destructive` patches pause the loop. The loop
is bounded by `max_attempts`.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from contig.bundle import (
    compute_annotation_identity,
    compute_output_checksums,
    compute_reference_identity,
    write_bundle,
)
from contig.corpus import append_case, failure_case_from_run
from contig.detect import diagnose_failure
from contig.events import parse_resource_usage_file
from contig.models import Diagnosis, ExecutionTarget, Patch, QCResult, RepairStep, RunRecord, RunSummary
from contig.notify import emit_event
from contig.reference_check import fasta_contigs, gtf_contigs
from contig.registry import VARIANT_ASSAYS, assay_for_pipeline
from contig.repair import propose_patches
from contig.resource_sizing import (
    PEAK_RSS_SAFETY_FACTOR,
    WALLTIME_SAFETY_FACTOR,
    TimeSizing,
    peak_informed_memory_gb,
    realtime_informed_time_h,
)
from contig.runner import (
    Executor,
    IndexBuilder,
    PipelineExecutionError,
    default_executor,
    default_index_builder,
    read_run_log,
    read_task_errors,
    run_pipeline,
)

_DEFAULT_MEMORY_GB = 8
_DEFAULT_TIME_HOURS = 4

CEILING_MEMORY_GB = 128
CEILING_TIME_H = 72

# A diagnosis below this confidence is treated as ambiguous: even a single gated
# fix is offered as a choice rather than a take-it-or-leave-it confirm (contract D).
_AMBIGUOUS_CONFIDENCE = 0.5

# Matches a non-whitespace, non-quote token ending in one of the supported
# single-file index extensions (.fai/.bai/.tbi/.csi/.dict; relative or absolute
# path, and `.dict` may arrive as a file:// URI which the deriver strips later).
# The character class [^\s"']+ excludes leading quote characters so a path
# printed inside double-quotes (e.g. `"aln.bam.bai"`) is extracted without the
# surrounding quotes.  The lookahead pins the token end (whitespace,
# end-of-line, or a trailing punctuation mark including quotes) so a longer
# token like "ref.fasta.fai_backup" is NOT mis-parsed as "ref.fasta.fai".
_INDEX_TOKEN_RE = re.compile(r"""[^\s"']+\.(fai|bai|tbi|csi|dict)(?=\s|$|[:,;"'])""")

# STAR's missing-index FATAL ERROR names the failing genomeDir as the PARENT of
# genomeParameters.txt; capture that directory token. The version-incompatible
# error carries no path, so this simply does not match there.
_STAR_GENOMEDIR_RE = re.compile(r"(\S+)/genomeParameters\.txt")


def _is_star_signature(line: str) -> bool:
    """True when an evidence line is a STAR (directory) genome-index failure.

    Matches the missing-index phrasing (``genomeParameters.txt`` /
    ``could not open genome file``) or the version-incompatible phrasing
    (``Genome version`` AND ``INCOMPATIBLE`` on the same line).
    """
    low = line.lower()
    if "genomeparameters.txt" in low or "could not open genome file" in low:
        return True
    return "genome version" in low and "incompatible" in low


def _parse_missing_index(diagnosis: Diagnosis) -> tuple[str, str] | None:
    """Scan diagnosis.evidence and classify the missing index as a kind.

    Returns ``(path, kind)`` where:

    - For a single-file index token the kind is its extension
      (``".fai"/".bai"/".tbi"/".csi"/".dict"``) and ``path`` is the token, e.g.
      ``("aln.bam.bai", ".bai")``. Single-file tokens WIN: scanned first, so a
      STAR signature never shadows them.
    - For a STAR (directory) index the kind is ``"star"`` and ``path`` is the
      failing genomeDir parsed from a ``could not open genome file
      <DIR>/genomeParameters.txt`` line (the PARENT dir), or ``""`` when the
      evidence carries no path (the version-incompatible line) — the build step
      then resolves the genomeDir from ``params["star_index"]``.

    Returns None if no supported index is found. Pure — no I/O.
    """
    for line in diagnosis.evidence:
        m = _INDEX_TOKEN_RE.search(line)
        if m:
            return m.group(), "." + m.group(1)
    if any(_is_star_signature(line) for line in diagnosis.evidence):
        genome_dir = ""
        for line in diagnosis.evidence:
            gm = _STAR_GENOMEDIR_RE.search(line)
            if gm:
                genome_dir = gm.group(1)
                break
        return genome_dir, "star"
    return None


# How to find the *source* an index is built from, given the index path. Most
# kinds just strip the index suffix; .dict must probe the filesystem for a
# companion FASTA (its source is not the indexed-path-minus-suffix).
#   (index_path, ext, run_dir) -> source path, or None if unresolvable.
SourceDeriver = Callable[[str, str, Path], "str | None"]


def _strip_suffix(index_path: str, ext: str, run_dir: Path) -> str | None:
    """Pure suffix-strip deriver for .fai/.bai/.tbi/.csi. Ignores run_dir."""
    return index_path.removesuffix(ext)


# FASTA companions a GATK sequence dictionary may sit beside, in priority order.
# Named once so a future kind can reuse the list.
_DICT_FASTA_EXTS = (".fasta", ".fa", ".fasta.gz", ".fa.gz")


def _resolve_dict_source(index_path: str, ext: str, run_dir: Path) -> str | None:
    """Resolve the source FASTA for a missing GATK ``.dict``.

    Replaces the ``.dict`` suffix with the first EXISTING of ``.fasta``, ``.fa``,
    ``.fasta.gz``, ``.fa.gz`` (priority order), looked up relative to the
    ``.dict`` path's OWN parent directory (absolute-safe). A relative ``.dict``
    is probed under ``run_dir``. A leading ``file://`` scheme (some GATK builds
    print a URI) is stripped first. Returns the resolved FASTA path, or None if
    no companion exists. Unlike the suffix-strip derivers this one touches the
    filesystem.
    """
    raw = index_path.removeprefix("file://")
    p = Path(raw)
    base_parent, stem = p.parent, p.name[: -len(ext)]
    for cand_ext in _DICT_FASTA_EXTS:
        cand = base_parent / f"{stem}{cand_ext}"
        probe = cand if cand.is_absolute() else Path(run_dir) / cand
        if probe.exists():
            return str(cand)
    return None


# Table-driven index builder: ``{ext: (derive_source, build_argv)}``. Adding a
# new index kind is a one-row change. The argv builder takes ``(src, idx)`` —
# suffix-strip kinds ignore ``idx``; ``.dict`` needs it (the output IS the
# missing index path).
_INDEX_BUILD: dict[str, tuple[SourceDeriver, Callable[[str, str], list[str]]]] = {
    ".fai": (_strip_suffix, lambda src, idx: ["samtools", "faidx", src]),
    ".bai": (_strip_suffix, lambda src, idx: ["samtools", "index", src]),
    ".tbi": (_strip_suffix, lambda src, idx: ["tabix", "-p", "vcf", src]),
    ".csi": (_strip_suffix, lambda src, idx: ["bcftools", "index", src]),
    ".dict": (_resolve_dict_source, lambda src, idx: ["samtools", "dict", "-o", idx, src]),
}


def _index_build_command(index_path: str, ext: str, run_dir: Path) -> list[str] | None:
    """Return the command to build the index at index_path, or None if its
    source cannot be resolved.

    Consults the ``_INDEX_BUILD`` table: the deriver finds the source the index
    is built from, then the argv builder dispatches to the correct tool:

      .fai  → ["samtools", "faidx", <fasta>]
      .bai  → ["samtools", "index", <bam>]
      .tbi  → ["tabix", "-p", "vcf", <vcf.gz>]
      .csi  → ["bcftools", "index", <vcf.gz>]
      .dict → ["samtools", "dict", "-o", <ref.dict>, <resolved-fasta>]

    Suffix-strip kinds are pure; the ``.dict`` deriver probes the filesystem and
    returns None (→ this returns None) when no companion FASTA exists.
    """
    entry = _INDEX_BUILD.get(ext)
    if entry is None:
        raise ValueError(f"unsupported index extension: {ext}")
    deriver, argv_fn = entry
    source = deriver(index_path, ext, run_dir)
    if source is None:
        return None
    return argv_fn(source, index_path)


def _write_status(run_dir: Path, state: str) -> None:
    """Write runs/<id>/status.json so a run is observable while in flight.

    run_record.json only appears at the end, so the dashboard reads this marker
    to tell "running" from "finished"/"error". started_at is preserved across
    updates; finished_at is set once the run leaves the running state.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "status.json"
    now = datetime.now(timezone.utc).isoformat()
    started_at = now
    if path.exists():
        try:
            started_at = json.loads(path.read_text()).get("started_at", now)
        except (ValueError, OSError):
            started_at = now
    path.write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "state": state,
                "pid": os.getpid(),
                "started_at": started_at,
                "finished_at": None if state == "running" else now,
            }
        )
    )


def _record_attempt(
    run_dir: Path, repair_history: list[RepairStep], step: RepairStep
) -> None:
    """Append a resolved attempt to repair_history and to repair_progress.jsonl.

    The jsonl line is written the moment the attempt resolves so a live view can
    show attempts as they happen; it mirrors what later lands in repair_history
    (PRD contract B). The file stays absent until the first failure.
    """
    repair_history.append(step)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "repair_progress.jsonl", "a") as fh:
        fh.write(step.model_dump_json() + "\n")


def _safe_patch(patches: list[Patch]) -> Patch | None:
    return next((p for p in patches if p.risk == "safe"), None)


def _gated_candidates(patches: list[Patch]) -> list[Patch]:
    """The non-safe (gated) patches, kept in their proposed best-first order."""
    return [p for p in patches if p.risk != "safe"]


def _is_ambiguous(diagnosis, gated: list[Patch]) -> bool:
    """True when the gated decision should be a CHOICE rather than a single confirm.

    Ambiguous (contract D) when the diagnosis confidence is below the threshold, OR
    when there is more than one viable non-safe candidate and no single safe fix.
    Reached only on the gated path (caller has already established no safe patch).
    """
    return diagnosis.confidence < _AMBIGUOUS_CONFIDENCE or len(gated) > 1


def _validated_choice(
    options: list[Patch], decision: object, choice: object
) -> Patch | None:
    """The chosen option iff the decision approves with a valid in-range index.

    A reject, a timeout (no decision), an approve with no choice, or an out-of-range
    index all return None: the choice is refused, never silently coerced (contract D).
    """
    if decision != "approve" or not isinstance(choice, int) or isinstance(choice, bool):
        return None
    if 0 <= choice < len(options):
        return options[choice]
    return None


def _choice_refusal_outcome(decision: object, choice: object, n_options: int) -> str:
    """Why a choice gate did not apply: rejected, timed out, or an invalid choice."""
    if decision == "reject":
        return "rejected_by_user"
    if decision == "approve":
        # Approved, but the choice was missing or out of range: not actionable.
        return "invalid_choice_rejected"
    return "approval_timed_out"


# A poll function blocks until an approval decision lands or the timeout elapses,
# returning the decision dict (`{"decision": "approve"|"reject", ...}`) or None on
# timeout. Injected in tests so they never sleep for real.
ApprovalPoll = Callable[[Path, float], "dict | None"]


def _write_pending_approval(
    run_dir: Path, run_id: str, attempt: int, diagnosis, patch: Patch, timeout_sec: float
) -> None:
    """Write pending_approval.json: the gated patch a human is being asked to decide.

    The dashboard reads this to render the Approve/Reject prompt (PRD contract C).
    """
    (run_dir / "pending_approval.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "attempt": attempt,
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "timeout_sec": timeout_sec,
                "decision_kind": "single",
                "diagnosis": {
                    "failure_class": diagnosis.failure_class,
                    "root_cause": diagnosis.root_cause,
                    "confidence": diagnosis.confidence,
                },
                "patch": {
                    "kind": patch.kind,
                    "risk": patch.risk,
                    "rationale": patch.rationale,
                    "operation": patch.operation,
                    "expected_signal": patch.expected_signal,
                },
            }
        )
    )


def _write_pending_choice(
    run_dir: Path,
    run_id: str,
    attempt: int,
    diagnosis,
    options: list[Patch],
    timeout_sec: float,
) -> None:
    """Write pending_approval.json for an AMBIGUOUS gate: a ranked choice (contract D).

    Carries an `options` array (ranked best-first) and `decision_kind: "choice"`,
    ALONGSIDE the existing single-patch fields (the best option) for back-compat, so
    an older dashboard still renders something. The human picks an option index in
    approval.json; the loop validates it against the options length.
    """
    best = options[0]
    (run_dir / "pending_approval.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "attempt": attempt,
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "timeout_sec": timeout_sec,
                "decision_kind": "choice",
                "diagnosis": {
                    "failure_class": diagnosis.failure_class,
                    "root_cause": diagnosis.root_cause,
                    "confidence": diagnosis.confidence,
                },
                "options": [
                    {
                        "index": index,
                        "kind": option.kind,
                        "risk": option.risk,
                        "rationale": option.rationale,
                        "expected_signal": option.expected_signal,
                    }
                    for index, option in enumerate(options)
                ],
                "patch": {
                    "kind": best.kind,
                    "risk": best.risk,
                    "rationale": best.rationale,
                    "operation": best.operation,
                    "expected_signal": best.expected_signal,
                },
            }
        )
    )


def _clear_pending_approval(run_dir: Path) -> None:
    path = run_dir / "pending_approval.json"
    if path.exists():
        path.unlink()


def _poll_approval_file(run_dir: Path, timeout_sec: float, interval: float = 1.0) -> dict | None:
    """Default poll: wait for approval.json up to timeout_sec, then give up.

    Reads `{decision, decided_at, by?}` once the file appears. A malformed file is
    treated as no decision yet (the human re-writes it).
    """
    path = run_dir / "approval.json"
    deadline = time.monotonic() + timeout_sec
    while True:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (ValueError, OSError):
                pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))


def _lead_number(value: object, default: int) -> float:
    """Leading numeric part of a Nextflow resource literal ('16.GB' -> 16.0)."""
    if value is None:
        return float(default)
    match = re.match(r"[\d.]+", str(value).strip())
    return float(match.group()) if match else float(default)


def _resource_ceiling_block(diagnosis, target, ceiling) -> str | None:
    """Message if the resource this failure class scales is already at/above its
    cap (so auto-scaling can grow it no further); else None."""
    if diagnosis.failure_class == "oom":
        if _lead_number(target.resource_limits.get("memory"), _DEFAULT_MEMORY_GB) >= ceiling["memory"]:
            return f"Out of memory persists at the {ceiling['memory']} GB ceiling; needs a node with more memory."
    if diagnosis.failure_class == "time_limit":
        if _lead_number(target.resource_limits.get("time"), _DEFAULT_TIME_HOURS) >= ceiling["time"]:
            return f"Time limit persists at the {ceiling['time']} h ceiling; needs a longer walltime allowance."
    return None


def _oom_memory_sizing(diagnosis, run_dir, events) -> tuple[int | None, str | None]:
    """Size an OOM memory retry from the run's observed peak RSS.

    For an OOM failure, parse the run's (partial) trace and size the retry to the
    failed task's observed peak via ``peak_informed_memory_gb`` (own observed peak
    -> blind fallback), returning the pre-clamp target GB for
    ``apply_patch`` plus a ``RepairStep.detail`` telemetry line. For any other
    failure class this is a no-op ``(None, None)`` -- sizing only touches OOM /
    memory; the blind ``x2`` bump and the ``time_limit`` branch are unchanged.
    """
    if diagnosis.failure_class != "oom":
        return None, None
    trace_path = run_dir / "trace.txt"
    usage = parse_resource_usage_file(trace_path) if trace_path.exists() else []
    sizing = peak_informed_memory_gb(events, usage)
    if sizing.target_gb is not None:
        detail = (
            f"scaled memory to ~{sizing.target_gb} GB from observed peak "
            f"{sizing.observed_peak_mb:.0f} MB (x{PEAK_RSS_SAFETY_FACTOR}, {sizing.tier})"
        )
    else:
        detail = "no usable observed peak; blind x2 fallback (unavailable)"
    return sizing.target_gb, detail


def _time_limit_sizing(diagnosis, run_dir, events) -> tuple[int | None, TimeSizing | None]:
    """Size a time_limit retry from the run's observed realtime.

    The walltime mirror of ``_oom_memory_sizing``: parse the run's (partial) trace
    and size the retry to the longest observed realtime via
    ``realtime_informed_time_h``, returning the RAW pre-clamp target hours for
    ``apply_patch`` plus the ``TimeSizing`` itself so the caller can build the
    ``RepairStep.detail`` off the APPLIED (post floor-at-blind / ceiling-clamp)
    time rather than the raw sized value. A no-op ``(None, None)`` for any other
    failure class -- sizing only touches ``time_limit``; the blind ``x2`` bump and
    the OOM branch are unchanged.
    """
    if diagnosis.failure_class != "time_limit":
        return None, None
    trace_path = run_dir / "trace.txt"
    usage = parse_resource_usage_file(trace_path) if trace_path.exists() else []
    sizing = realtime_informed_time_h(events, usage)
    return sizing.target_h, sizing


def _time_limit_detail(target, sizing, prev_time_h) -> str:
    """Build the ``RepairStep.detail`` for a time_limit heal from the APPLIED time.

    ``prev_time_h`` is the pre-patch walltime, so ``blind = prev_time_h * 2`` is the
    old blind bump the observed override was floored against; ``sizing.target_h`` is
    the raw sized value. Reading the applied hours off the patched target keeps the
    telemetry honest to what actually shipped (a realtime at a walltime kill is a
    censored lower bound, so ``apply_patch`` floors the override at blind).
    """
    if sizing.target_h is None:
        return "no usable observed realtime; blind x2 fallback (unavailable)"
    applied_h = int(_lead_number(target.resource_limits.get("time"), _DEFAULT_TIME_HOURS))
    blind = prev_time_h * 2
    verb = "beat" if sizing.target_h > blind else "tied"
    return (
        f"scaled time to ~{applied_h}h from observed realtime "
        f"{sizing.observed_realtime_sec:.0f}s (x{WALLTIME_SAFETY_FACTOR}, {sizing.tier}); "
        f"{verb} blind x2"
    )


def apply_patch(
    target: ExecutionTarget,
    patch: Patch,
    params: dict[str, object] | None = None,
    *,
    ceiling: dict[str, int] | None = None,
    observed_target_gb: int | None = None,
    observed_target_h: int | None = None,
) -> tuple[ExecutionTarget, dict[str, object]]:
    """Apply a patch to the run inputs, returning the updated (target, params).

    Bounded by kind (PRD contract C/D):

    - `resource`: bump `process.resourceLimits` (what modern nf-core honors; the
      old `--max_memory` params are ignored). The `ceiling` kwarg (default:
      ``{"memory": CEILING_MEMORY_GB, "time": CEILING_TIME_H}``) sets an absolute
      upper bound on each auto-scaled value. A pre-existing value that already
      exceeds the ceiling is preserved as-is (never-shrink rule). When
      ``observed_target_gb`` is supplied it overrides the blind memory
      multiplier as the pre-clamp target; the ceiling clamp and never-shrink
      rule still apply to it unchanged. When ``observed_target_h`` is supplied it
      overrides the blind time multiplier, but is FLOORED at the blind ×N bump
      (``max(observed, blind)``) -- unlike memory -- because a walltime
      ``realtime`` observation is a censored lower bound and must never make the
      retry weaker than today's blind bump. The ceiling clamp and never-shrink
      rule then apply unchanged.
    - `param`: merge `set_param` (its concrete key/value swap) into the pipeline
      params so the corrected parameter reaches the re-run's command.
    - `reference`: merge `set_param` (the reference swap, e.g. igenomes_ignore)
      into the params. A reference patch WITHOUT set_param leaves params
      unchanged here. A `build_index` reference patch is handled one level up by
      `_apply_patch_and_maybe_build` (which actually builds the index — that build
      IS the fix); `apply_patch` itself stays a no-op for it, so the re-run picks
      up the freshly built index.
    - `env`: merge the operation into the target's backend_options (string-coerced
      so it rides into the generated config / re-run target).
    - `code`/`retry`: change nothing. The re-run itself is the fix.
    """
    if ceiling is None:
        ceiling = {"memory": CEILING_MEMORY_GB, "time": CEILING_TIME_H}
    params = dict(params or {})
    if patch.kind == "resource":
        mult = patch.operation.get("multiply", {})
        limits = dict(target.resource_limits)
        if "memory" in mult:
            current = _lead_number(limits.get("memory"), _DEFAULT_MEMORY_GB)
            bumped = (
                observed_target_gb
                if observed_target_gb is not None
                else int(current * int(mult["memory"]))
            )
            capped = min(bumped, ceiling["memory"])
            final = max(capped, int(current))
            limits["memory"] = f"{final}.GB"
        if "time" in mult:
            current = _lead_number(limits.get("time"), _DEFAULT_TIME_HOURS)
            blind = int(current * int(mult["time"]))
            bumped = max(observed_target_h, blind) if observed_target_h is not None else blind
            capped = min(bumped, ceiling["time"])
            final = max(capped, int(current))
            limits["time"] = f"{final}.h"
        return target.model_copy(update={"resource_limits": limits}), params
    if patch.kind in ("param", "reference"):
        # set_param carries the concrete swap (a corrected param, or a reference
        # knob like igenomes_ignore) merged into params so it reaches the re-run.
        # A reference patch with no set_param stays re-run only (unchanged params).
        swap = patch.operation.get("set_param")
        if isinstance(swap, dict):
            params.update(swap)
        return target, params
    if patch.kind == "env":
        options = dict(target.backend_options)
        options.update({k: str(v) for k, v in patch.operation.items()})
        return target.model_copy(update={"backend_options": options}), params
    return target, params


def _build_star_index(
    target: ExecutionTarget,
    params: dict[str, object],
    *,
    parsed_path: str,
    run_dir: Path,
    index_builder: IndexBuilder,
    built_paths: set[str],
) -> tuple[ExecutionTarget, dict[str, object], str, str | None, bool]:
    """Rebuild a STAR genome index into a run-scoped scratch dir and redirect.

    STAR's version-incompatible error carries NO path, so the failing genomeDir
    is ``parsed_path`` (from the missing-index line) or, failing that,
    ``params["star_index"]``. The build never touches the user's genomeDir: it
    writes a fresh index under ``run_dir/healed_index/star`` and, on success,
    redirects the retry by setting ``params["star_index"]`` to the scratch path.

    Branches honestly (mirrors the single-file build outcomes):
      * no resolvable genomeDir       → ``index_unresolvable``
      * no fasta in params            → ``index_unresolvable``
      * genomeDir already rebuilt     → ``index_build_failed`` (give up)
      * non-zero build                → ``index_build_failed``
      * rc 0 but empty scratch dir    → ``index_build_failed`` (no index produced)
      * success                       → ``built_index_and_retried`` (redirected)

    Bounded to ONE build per run: both the failing genomeDir AND the scratch
    path are added to ``built_paths`` on build. The version-incompatible error
    carries no path, so a SECOND such failure resolves its failing genomeDir
    from ``params["star_index"]`` — which, after a successful build, IS the
    scratch path. Recognizing the scratch path as already-built closes that
    loophole: it gives up honestly instead of rebuilding into the same scratch
    dir a second time. The scratch dir is also wiped fresh (``rmtree`` then
    ``mkdir``) before each build so leftover residue can never masquerade as
    this build's output in the non-empty success gate.
    """
    failing_dir = parsed_path or str(params.get("star_index") or "")
    if not failing_dir:
        return (
            target,
            params,
            "index_unresolvable",
            "Could not resolve the STAR genome index directory to rebuild.",
            False,
        )
    fasta = params.get("fasta")
    if not fasta:
        return (
            target,
            params,
            "index_unresolvable",
            f"Could not resolve a FASTA to rebuild the STAR index {failing_dir}.",
            False,
        )
    if failing_dir in built_paths:
        return (
            target,
            params,
            "index_build_failed",
            f"Already rebuilt {failing_dir}; failure persists.",
            False,
        )
    scratch = Path(run_dir) / "healed_index" / "star"
    # Fresh scratch dir: wipe any residue (e.g. from a stale prior state) so the
    # non-empty success gate below reflects only THIS build's output.
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True, exist_ok=True)
    argv = [
        "STAR",
        "--runMode",
        "genomeGenerate",
        "--genomeDir",
        str(scratch),
        "--genomeFastaFiles",
        str(fasta),
    ]
    gtf = params.get("gtf")
    if gtf:
        argv += ["--sjdbGTFfile", str(gtf)]
    # Bound the rebuild to ONE per run: mark both the failing genomeDir and the
    # scratch dir as built, so a second failure whose failing_dir resolves to
    # the scratch path (post-redirect) is recognized as already-built too.
    built_paths.add(failing_dir)
    built_paths.add(str(scratch))
    rc = index_builder(argv, run_dir)
    if rc != 0:
        return (
            target,
            params,
            "index_build_failed",
            f"Building the STAR index for {failing_dir} failed (exit {rc}).",
            False,
        )
    if not (scratch.is_dir() and any(scratch.iterdir())):
        return (
            target,
            params,
            "index_build_failed",
            f"The STAR index build for {failing_dir} produced no index.",
            False,
        )
    params["star_index"] = str(scratch)
    version = _read_star_genome_version(scratch)
    detail = (
        f"Built STAR index (genome version {version}) into {scratch}."
        if version
        else f"Built STAR index into {scratch}."
    )
    return target, params, "built_index_and_retried", detail, True


def _read_star_genome_version(scratch: Path) -> str | None:
    """Best-effort read of the ``versionGenome`` value from a freshly-built
    STAR index's ``genomeParameters.txt`` (S1, OQ1).

    Tolerant of a tab- or space-separated line (``versionGenome\\t2.7.4a`` or
    ``versionGenome 2.7.4a``). Returns None — never raises — when the file is
    absent, unreadable, or carries no ``versionGenome`` line: a missing version
    must never fail the heal.
    """
    try:
        text = (scratch / "genomeParameters.txt").read_text()
    except OSError:
        return None
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] == "versionGenome":
            version = parts[1].strip()
            if version:
                return version
    return None


def _gzip_kind(path: str | Path) -> str:
    """Classify a file as ``"plain_gzip"``, ``"bgzf"``, or ``"not_gzip"``.

    BGZF is a valid gzip stream whose first member carries a FLG.FEXTRA
    subfield tagged ``SI1='B', SI2='C'`` (the samtools/htslib "BC" marker).
    Distinguishing it from a plain gzip stream matters because a valid BGZF
    reference must be left untouched (R2): recompressing it would be
    pointless churn on an already-correct file. Never raises — a short,
    unreadable, or malformed file is honestly reported as ``"not_gzip"``.
    """
    try:
        with open(path, "rb") as fh:
            header = fh.read(12)
            if len(header) < 12 or header[0:2] != b"\x1f\x8b":
                return "not_gzip"
            if not (header[3] & 0x04):
                return "plain_gzip"
            xlen = int.from_bytes(header[10:12], "little")
            extra = fh.read(xlen)
    except OSError:
        return "not_gzip"
    # Walk the FEXTRA subfields looking for the "BC" (SI1=0x42, SI2=0x43) tag.
    i = 0
    while i + 4 <= len(extra):
        si1, si2 = extra[i], extra[i + 1]
        slen = int.from_bytes(extra[i + 2 : i + 4], "little")
        if si1 == 0x42 and si2 == 0x43:
            return "bgzf"
        i += 4 + slen
    return "plain_gzip"


def _recompress_reference(
    target: ExecutionTarget,
    params: dict[str, object],
    *,
    run_dir: Path,
    built_paths: set[str],
) -> tuple[ExecutionTarget, dict[str, object], str, str | None, bool]:
    """Decompress a plain-gzip reference FASTA into a run-scoped scratch copy.

    samtools faidx requires BGZF (or uncompressed) FASTA, not plain gzip. This
    stream-decompresses the reference with stdlib ``gzip`` (no external tool —
    the fix target is a plain uncompressed ``.fa``, see plan §0) into
    ``run_dir/healed_reference`` and, on success, redirects the retry by
    setting ``params["fasta"]`` to the scratch path. The user's original file
    is never touched.

    Branches honestly, mirroring ``_build_star_index``'s shape:
      * no ``fasta`` in params        → ``reference_recompress_unresolvable``
      * fasta already recompressed    → ``reference_recompress_unresolvable`` (give up)
      * fasta is not plain gzip       → ``reference_recompress_unresolvable`` (BGZF or
                                          not-gzip left untouched — R2)
      * decompression raises          → ``reference_recompress_failed``
      * success                       → ``recompressed_reference_and_retried`` (redirected)

    Bounded to ONE recompress per run: both the original fasta and the
    scratch target are added to ``built_paths`` before decompressing, so a
    persisting failure after a successful recompress gives up instead of
    looping.
    """
    fasta = params.get("fasta")
    if not fasta:
        return (
            target,
            params,
            "reference_recompress_unresolvable",
            "No FASTA in params to recompress.",
            False,
        )
    fasta = str(fasta)
    if fasta in built_paths:
        return (
            target,
            params,
            "reference_recompress_unresolvable",
            f"Already recompressed {fasta}; failure persists.",
            False,
        )
    kind = _gzip_kind(fasta)
    if kind != "plain_gzip":
        reason = "is already BGZF-compressed" if kind == "bgzf" else "is not gzip-compressed"
        return (
            target,
            params,
            "reference_recompress_unresolvable",
            f"Reference {fasta} {reason}; nothing to recompress.",
            False,
        )
    scratch = Path(run_dir) / "healed_reference"
    # Fresh scratch dir: wipe any residue before each recompress (mirrors STAR).
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True, exist_ok=True)
    basename = Path(fasta).name
    stem = basename[: -len(".gz")] if basename.endswith(".gz") else basename
    target_file = scratch / stem
    # Bound the recompress to ONE per run: mark both the original fasta and
    # the scratch target as built before decompressing.
    built_paths.add(fasta)
    built_paths.add(str(target_file))
    try:
        with gzip.open(fasta, "rb") as src, open(target_file, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1 << 20)
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        return (
            target,
            params,
            "reference_recompress_failed",
            f"Decompressing {fasta} failed: {exc}.",
            False,
        )
    params["fasta"] = str(target_file)
    detail = f"Decompressed {fasta} into {target_file} (plain gzip is not BGZF-indexable)."
    return target, params, "recompressed_reference_and_retried", detail, True


def _apply_patch_and_maybe_build(
    target: ExecutionTarget,
    patch: Patch,
    params: dict[str, object],
    *,
    diagnosis: Diagnosis,
    run_dir: Path,
    index_builder: IndexBuilder,
    built_paths: set[str],
    ceiling: dict[str, int] | None,
    default_outcome: str,
) -> tuple[ExecutionTarget, dict[str, object], str, str | None, bool]:
    """Apply a gated patch, and if it's a build_index/recompress_reference
    reference patch, do that work too.

    Returns ``(target, params, outcome, detail, continue_)``:

    - A non-build, non-recompress patch applies normally and returns
      ``(default_outcome, None, True)`` — the loop should retry.
    - A ``recompress_reference`` reference patch delegates entirely to
      ``_recompress_reference`` (see its docstring for the full branch table):
      it decompresses a plain-gzip FASTA into a run-scoped scratch copy and
      redirects the retry, or gives up honestly (unresolvable / already-BGZF /
      decompress failure / already recompressed this run).
    - A ``build_index`` reference patch parses the missing index path from the
      diagnosis (supports .fai/.bai/.tbi/.csi/.dict) and runs the builder.
      Branches honestly:
        * unparseable path  → ``("index_unresolvable", <detail>, False)`` (give up).
        * unresolvable source (deriver returns None — e.g. a .dict with no FASTA
          companion on disk) → ``("index_unresolvable", <detail naming path>, False)``.
        * already built this run (``index_path in built_paths``) → give up:
          ``("index_build_failed", "Already rebuilt …; failure persists.", False)``.
        * non-zero build    → ``("index_build_failed", <detail naming path>, False)``.
        * success           → ``("built_index_and_retried", None, True)`` (retry).

    ``built_paths`` is the set of index paths already built in THIS run; it
    bounds the loop to at most one build per distinct index path.

    The build IS the fix (apply_patch is a no-op for build_index), so the re-run
    picks up the freshly built index from ``run_dir``.
    """
    target, params = apply_patch(target, patch, params, ceiling=ceiling)
    if patch.kind == "reference" and patch.operation.get("recompress_reference"):
        return _recompress_reference(target, params, run_dir=run_dir, built_paths=built_paths)
    if not (patch.kind == "reference" and patch.operation.get("build_index")):
        return target, params, default_outcome, None, True
    parsed = _parse_missing_index(diagnosis)
    if parsed is None:
        return (
            target,
            params,
            "index_unresolvable",
            "Could not parse a missing index path from the failure.",
            False,
        )
    index_path, kind = parsed
    if kind == "star":
        # STAR's index is a DIRECTORY; the version-incompatible failure has no
        # path, so the genomeDir is resolved here (from params) and rebuilt into
        # scratch with a redirect — not via the single-file _index_build_command.
        return _build_star_index(
            target,
            params,
            parsed_path=index_path,
            run_dir=run_dir,
            index_builder=index_builder,
            built_paths=built_paths,
        )
    ext = kind
    if index_path in built_paths:
        # We already built this exact index once this run and the failure came
        # back the same way (e.g. a wrong reference masquerading as a missing
        # dict). Rebuilding it again can't help — give up honestly instead of
        # burning the remaining attempts on identical rebuilds.
        return (
            target,
            params,
            "index_build_failed",
            f"Already rebuilt {index_path}; failure persists.",
            False,
        )
    cmd = _index_build_command(index_path, ext, run_dir)
    if cmd is None:
        return (
            target,
            params,
            "index_unresolvable",
            f"Could not resolve a source to build {index_path}.",
            False,
        )
    built_paths.add(index_path)
    rc = index_builder(cmd, run_dir)
    if rc != 0:
        return (
            target,
            params,
            "index_build_failed",
            f"Building the index for {index_path} failed (exit {rc}).",
            False,
        )
    return target, params, "built_index_and_retried", None, True


def self_heal_run(
    *,
    pipeline: str,
    revision: str,
    profiles: list[str],
    target: ExecutionTarget,
    input_paths: list,
    runs_dir,
    run_id: str,
    executor: Executor = default_executor,
    index_builder: IndexBuilder = default_index_builder,
    params: dict[str, object] | None = None,
    nextflow_version: str | None = None,
    max_attempts: int = 3,
    assay: str = "rnaseq",
    pending_corpus: str | Path | None = None,
    resume: bool = False,
    auto_approve: bool = False,
    approval_timeout: float = 1800,
    poll: ApprovalPoll = _poll_approval_file,
    propose: Callable[..., list[Patch]] = propose_patches,
    notify_webhook: str | None = None,
    resource_ceiling: dict[str, int] | None = None,
    harmonized_reference_direction: str | None = None,
) -> RunRecord:
    """Run a pipeline and auto-recover from recoverable failures, logging the chain.

    Every failed attempt is also stashed to a pending-review failure corpus
    (`pending_corpus`, default `<runs_dir>/pending_corpus.jsonl`) with the
    detector's diagnosis as a PROVISIONAL label, so the corpus grows from real
    runs. These are separate from the golden corpus until a human confirms them.
    """
    run_dir = (Path(runs_dir) / run_id).resolve()
    _write_status(run_dir, "running")
    resource_ceiling = resource_ceiling or {"memory": CEILING_MEMORY_GB, "time": CEILING_TIME_H}
    pending_path = Path(pending_corpus) if pending_corpus else Path(runs_dir) / "pending_corpus.jsonl"
    current_params = dict(params or {})
    current_target = target
    repair_history: list[RepairStep] = []
    # Index paths already built this run: bounds the loop to one build per path,
    # so a wrong-reference masquerade can't trigger a rebuild every attempt.
    built_paths: set[str] = set()
    attempt = 1

    while True:
        try:
            record = run_pipeline(
                pipeline=pipeline,
                revision=revision,
                profiles=profiles,
                target=current_target,
                input_paths=input_paths,
                runs_dir=runs_dir,
                run_id=run_id,
                executor=executor,
                params=current_params or None,
                nextflow_version=nextflow_version,
                resume=resume or attempt > 1,
                assay=assay,
            )
            return _finalize(
                record, repair_history, run_dir,
                runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                harmonized_reference_direction=harmonized_reference_direction,
            )
        except PipelineExecutionError as exc:
            events = exc.record.events if exc.record else []
            log_text = read_run_log(run_dir) + "\n" + read_task_errors(run_dir)
            diagnosis = diagnose_failure(events, log_text)
            # Stash this failure for the corpus with the detector's diagnosis as a
            # provisional label (pending human confirmation). Capture needs a
            # record (events) to be faithful; a trace-less failure has nothing.
            if exc.record is not None:
                append_case(
                    failure_case_from_run(
                        exc.record,
                        log_text,
                        diagnosis.failure_class,
                        case_id=f"{run_id}-attempt{attempt}",
                        source=f"pending:{run_id}",
                    ),
                    pending_path,
                )
            patches = propose(diagnosis)
            safe = _safe_patch(patches)

            if safe is None:
                # No automatic fix. If there's no patch at all there is nothing
                # left to try; if there's a gated patch, pause for a human
                # (or apply it now under --auto-approve).
                if not patches:
                    _record_attempt(
                        run_dir,
                        repair_history,
                        RepairStep(attempt=attempt, diagnosis=diagnosis, patch=None, outcome="gave_up"),
                    )
                    return _finalize(
                        exc.record, repair_history, run_dir,
                        runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                        harmonized_reference_direction=harmonized_reference_direction,
                    )

                candidates = _gated_candidates(patches)
                gated = candidates[0]
                if attempt >= max_attempts:
                    _record_attempt(
                        run_dir,
                        repair_history,
                        RepairStep(attempt=attempt, diagnosis=diagnosis, patch=gated, outcome="gave_up"),
                    )
                    return _finalize(
                        exc.record, repair_history, run_dir,
                        runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                        harmonized_reference_direction=harmonized_reference_direction,
                    )

                # --auto-approve is non-interactive: it always takes the best-ranked
                # gated fix, so there is no choice to make even when ambiguous.
                if auto_approve:
                    current_target, current_params, outcome, detail, cont = (
                        _apply_patch_and_maybe_build(
                            current_target, gated, current_params,
                            diagnosis=diagnosis, run_dir=run_dir,
                            index_builder=index_builder, built_paths=built_paths,
                            ceiling=resource_ceiling,
                            default_outcome="approved_and_retried",
                        )
                    )
                    _record_attempt(
                        run_dir,
                        repair_history,
                        RepairStep(attempt=attempt, diagnosis=diagnosis, patch=gated, outcome=outcome, detail=detail),
                    )
                    if not cont:
                        return _finalize(
                            exc.record, repair_history, run_dir,
                            runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                            harmonized_reference_direction=harmonized_reference_direction,
                        )
                    attempt += 1
                    continue

                if _is_ambiguous(diagnosis, candidates):
                    # AMBIGUOUS: present the ranked options and let the human pick one
                    # (contract D). approval.json carries {decision, choice}.
                    _write_pending_choice(
                        run_dir, run_id, attempt, diagnosis, candidates, approval_timeout
                    )
                    _write_status(run_dir, "awaiting_approval")
                    emit_event(
                        runs_dir, run_id, "awaiting_approval",
                        f"Run {run_id} is paused for a choice among {len(candidates)} fixes.",
                        webhook=notify_webhook,
                    )
                    result = poll(run_dir, approval_timeout) or {}
                    _clear_pending_approval(run_dir)
                    decision = result.get("decision")
                    choice = result.get("choice")

                    chosen = _validated_choice(candidates, decision, choice)
                    if chosen is not None:
                        current_target, current_params, outcome, detail, cont = (
                            _apply_patch_and_maybe_build(
                                current_target, chosen, current_params,
                                diagnosis=diagnosis, run_dir=run_dir,
                                index_builder=index_builder, built_paths=built_paths,
                            ceiling=resource_ceiling,
                                default_outcome="chose_and_retried",
                            )
                        )
                        _write_status(run_dir, "running")
                        _record_attempt(
                            run_dir,
                            repair_history,
                            RepairStep(attempt=attempt, diagnosis=diagnosis, patch=chosen, outcome=outcome, detail=detail),
                        )
                        if not cont:
                            return _finalize(
                                exc.record, repair_history, run_dir,
                                runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                                harmonized_reference_direction=harmonized_reference_direction,
                            )
                        attempt += 1
                        continue

                    outcome = _choice_refusal_outcome(decision, choice, len(candidates))
                    _record_attempt(
                        run_dir,
                        repair_history,
                        RepairStep(attempt=attempt, diagnosis=diagnosis, patch=gated, outcome=outcome),
                    )
                    return _finalize(
                        exc.record, repair_history, run_dir,
                        runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                        harmonized_reference_direction=harmonized_reference_direction,
                    )

                # The unambiguous single gated patch: a binary confirm gate.
                _write_pending_approval(
                    run_dir, run_id, attempt, diagnosis, gated, approval_timeout
                )
                _write_status(run_dir, "awaiting_approval")
                emit_event(
                    runs_dir, run_id, "awaiting_approval",
                    f"Run {run_id} is paused for approval on a {gated.kind} patch.",
                    webhook=notify_webhook,
                )
                result = poll(run_dir, approval_timeout)
                _clear_pending_approval(run_dir)
                decision = (result or {}).get("decision") if result else None

                if decision == "approve":
                    current_target, current_params, outcome, detail, cont = (
                        _apply_patch_and_maybe_build(
                            current_target, gated, current_params,
                            diagnosis=diagnosis, run_dir=run_dir,
                            index_builder=index_builder, built_paths=built_paths,
                            ceiling=resource_ceiling,
                            default_outcome="approved_and_retried",
                        )
                    )
                    _write_status(run_dir, "running")
                    _record_attempt(
                        run_dir,
                        repair_history,
                        RepairStep(attempt=attempt, diagnosis=diagnosis, patch=gated, outcome=outcome, detail=detail),
                    )
                    if not cont:
                        return _finalize(
                            exc.record, repair_history, run_dir,
                            runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                            harmonized_reference_direction=harmonized_reference_direction,
                        )
                    attempt += 1
                    continue

                outcome = "rejected_by_user" if decision == "reject" else "approval_timed_out"
                _record_attempt(
                    run_dir,
                    repair_history,
                    RepairStep(attempt=attempt, diagnosis=diagnosis, patch=gated, outcome=outcome),
                )
                return _finalize(
                    exc.record, repair_history, run_dir,
                    runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                    harmonized_reference_direction=harmonized_reference_direction,
                )

            if attempt >= max_attempts:
                _record_attempt(
                    run_dir,
                    repair_history,
                    RepairStep(attempt=attempt, diagnosis=diagnosis, patch=safe, outcome="gave_up"),
                )
                return _finalize(
                    exc.record, repair_history, run_dir,
                    runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                    harmonized_reference_direction=harmonized_reference_direction,
                )

            block = _resource_ceiling_block(diagnosis, current_target, resource_ceiling)
            if block is not None:
                _record_attempt(run_dir, repair_history,
                    RepairStep(attempt=attempt, diagnosis=diagnosis, patch=safe,
                               outcome="gave_up_at_ceiling", detail=block))
                return _finalize(exc.record, repair_history, run_dir,
                    runs_dir=runs_dir, run_id=run_id, webhook=notify_webhook,
                    harmonized_reference_direction=harmonized_reference_direction)

            observed_target_gb, mem_detail = _oom_memory_sizing(diagnosis, run_dir, events)
            observed_target_h, time_sizing = _time_limit_sizing(diagnosis, run_dir, events)
            prev_time_h = int(_lead_number(current_target.resource_limits.get("time"), _DEFAULT_TIME_HOURS))
            current_target, current_params = apply_patch(
                current_target, safe, current_params,
                ceiling=resource_ceiling,
                observed_target_gb=observed_target_gb,
                observed_target_h=observed_target_h,
            )
            # Only one of the two sizers is non-None per failure class (OOM vs
            # time_limit); the time detail is built AFTER apply_patch so it reports
            # the applied (post floor-at-blind / clamp) walltime, not the raw size.
            time_detail = (
                _time_limit_detail(current_target, time_sizing, prev_time_h)
                if time_sizing is not None
                else None
            )
            detail = mem_detail or time_detail
            _record_attempt(
                run_dir,
                repair_history,
                RepairStep(attempt=attempt, diagnosis=diagnosis, patch=safe,
                           outcome="patched_and_retried", detail=detail),
            )
            attempt += 1


def _unmatched_harmonized_contigs(params: dict[str, object]) -> list[str]:
    """Recompute the still-unmatched GTF contigs after harmonization.

    ``params["gtf"]`` at ``_finalize`` time is the HARMONIZED scratch path (the
    CLI swaps it in before calling ``self_heal_run``, see cli.py's pre-flight
    block): every GTF seqname with a FASTA match has already been renamed to
    its FASTA spelling. So whatever GTF seqname remains outside the FASTA
    contig set is exactly the set ``plan_harmonization`` recorded as
    ``HarmonizationPlan.unmatched`` — no need to thread that plan through the
    whole self_heal_run call chain. Degrades to `[]` (never a crash, never a
    fabricated list) if the paths are missing/unreadable, e.g. in tests that
    exercise the breadcrumb with fake paths.
    """
    fasta = params.get("fasta")
    gtf = params.get("gtf")
    if not fasta or not gtf:
        return []
    try:
        return sorted(gtf_contigs(gtf) - fasta_contigs(fasta))
    except OSError:
        return []


def _finalize(
    record: RunRecord | None,
    repair_history: list[RepairStep],
    run_dir: Path,
    *,
    runs_dir,
    run_id: str,
    webhook: str | None = None,
    harmonized_reference_direction: str | None = None,
) -> RunRecord:
    """Attach the repair history to the final record, persist it, and notify.

    Emits a terminal notification (PRD contract A): `finished` when the run's
    events show success, otherwise `failed` (a give-up, rejection, or timeout all
    finalize a failed record). A trace-less run produces no record and no
    terminal notification: there is nothing to report yet.
    """
    if record is None:
        # The run failed before producing any trace; nothing was captured.
        _write_status(run_dir, "error")
        raise PipelineExecutionError(1, None)
    record.repair_history = repair_history
    record.output_checksums = compute_output_checksums(_results_dir(record, run_dir))
    record.reference_identity = compute_reference_identity(record.parameters)
    # Annotation provenance capture (capability C7) is gated to the two variant
    # assays (germline shipped M1, somatic enabled M2) — other assays never had
    # an annotation step to attribute, and gating avoids attaching provenance to
    # an unrelated VCF that incidentally carries a CSQ/ANN-like token. Resolve
    # the assay exactly as the rest of the engine does (methods.py:119): prefer
    # the persisted `record.assay`, falling back to the legacy
    # pipeline-derived lookup. If NEITHER resolves the assay (a legacy record
    # predating both fields, or a pipeline the registry doesn't know), fall back
    # to attempting the capture rather than silently dropping provenance for a
    # possibly-genuine variant run — compute_annotation_identity itself already
    # degrades to an empty list when nothing is found, so this can never
    # fabricate one. M4: the list can hold BOTH a VEP and a SnpEff entry when
    # both annotators ran (deduped by tool; see compute_annotation_identity).
    resolved_assay = record.assay or assay_for_pipeline(record.pipeline)
    if resolved_assay is None or resolved_assay in VARIANT_ASSAYS:
        record.annotation_identity = compute_annotation_identity(run_dir)
    if harmonized_reference_direction and record.reference_identity is not None:
        record.harmonized_reference_direction = harmonized_reference_direction
        record.reference_identity.harmonized = True
        record.reference_identity.harmonized_direction = harmonized_reference_direction
        unmatched = _unmatched_harmonized_contigs(record.parameters)
        message = (
            f"Reference harmonized ({harmonized_reference_direction}) to match "
            f"the FASTA before the run. "
        )
        if unmatched:
            names = ", ".join(unmatched)
            message += (
                f"Note: {len(unmatched)} GTF contig(s) could not be matched to "
                f"the FASTA and were left as-is: {names}. "
            )
        message += "Confirm the reference was correct."
        record.qc_results.append(QCResult(
            kind="structural",
            check="reference_harmonized",
            status="warn",
            message=message,
        ))
    trace_path = Path(run_dir) / "trace.txt"
    if trace_path.exists():
        record.resource_usage = parse_resource_usage_file(trace_path)
    write_bundle(record, run_dir)
    _write_status(run_dir, "finished")
    succeeded = RunSummary.from_events(record.events).succeeded
    if succeeded:
        emit_event(runs_dir, run_id, "finished", f"Run {run_id} finished.", webhook=webhook)
    else:
        emit_event(runs_dir, run_id, "failed", f"Run {run_id} failed.", webhook=webhook)
    return record


def _results_dir(record: RunRecord, run_dir: Path) -> Path:
    """Where the run wrote its outputs: the pipeline outdir, else run_dir/results.

    The CLI absolutizes --outdir into record.parameters; a run launched without
    one (the test profile path) defaults to run_dir/results, mirroring the CLI.
    """
    outdir = record.parameters.get("outdir")
    return Path(str(outdir)) if outdir else Path(run_dir) / "results"
