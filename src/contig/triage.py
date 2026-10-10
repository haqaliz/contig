"""Injectable triage seam for `contig` (C9 slice 1: `jev-calibrated-triage`).

A `Triage` turns a `TriageRequest` (run id, surface, mode, and the
whitelisted egress payload) into a Contig-owned `TriageResult`. The default
seam is `NullTriage` -- the "no triage" result -- and `default_jev_triage`
is the real, env-gated, https-only transport. Every failure mode degrades
to the Null behavior: never raise, never change caller behavior.

R6 egress whitelist (single declaration `PAYLOAD_WHITELIST`):
the Jev request carries only numeric QC metrics and metadata -- each
check's numeric `value` plus `check`/`kind`/`status`/numeric
`expected_range` (never `message`), the run's numeric summary
(`task_counts`, `failed_tasks`, `repair_attempts`, the `verdict` string
rendered), and file `size`/`sha256` only. NEVER: raw reads, FASTQ/BAM/VCF
data or paths, read bytes, sample identifiers beyond the opaque `run_id`,
raw log text, or keys. The constructed payload is asserted in tests (mutation
control: raw-read markers can never appear).

R7 egress contract (transport):
`default_jev_triage` POSTs the whitelisted payload (Contig-owned JSON over
stdlib `urllib`) to the base URL in `CONTIG_JEV_URL` with a strict
`_TRIAGE_TIMEOUT = 30` s timeout and a size-bound
`_MAX_TRIAGE_RESPONSE_BYTES = 64 KiB` response. The endpoint must be
`https://` (the payload rides a bearer key): a non-https URL is refused by
the seam, except `http://localhost` for the manual live gate behind the
explicit `CONTIG_JEV_ALLOW_HTTP` opt-out (off by default). The reply JSON
`{"items": [{"id": ..., "confidence": 0-1}]}` is parsed defensively
(`parse_triage_response`); item ids are `{run_id}:{surface}:{check}`, so a
response item always addresses a real check in the payload.

Degrade-to-Null contract:
key absent/empty ⇒ no request constructed at all (asserted); URL
absent/empty/refused ⇒ no request; transport failure, timeout, HTTP error,
oversized response, or malformed reply ⇒ `TriageResult(mode="null", ...)`
with the cause named in `reason`. The seam never raises, and never logs or
otherwise emits `CONTIG_JEV_KEY` (only `os.environ.get` reads it).
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Mapping


@dataclass(frozen=True)
class TriageRequest:
    """One triage decision: a run's whitelisted payload on one surface.

    `surface` names the decision site (`qc_anomaly` for the self-heal QC
    verdict-trigger branch, `verify_concordance` for the verify-time
    concordance dispatch); `mode` is `shadow` (default when a key is present:
    everything runs, Jev is logged alongside) or `active` (below-threshold
    checks are skipped and recorded UNVERIFIED). `payload` is the R6
    whitelisted egress payload built by `build_triage_payload`.
    """

    run_id: str
    surface: Literal["qc_anomaly", "verify_concordance"]
    mode: Literal["shadow", "active"]
    payload: dict


@dataclass(frozen=True)
class TriageResult:
    """The seam's answer, always a Contig-owned shape.

    `mode` is `"null"` for the no-triage degrade (with `reason` set) or the
    request's mode (`"shadow"`/`"active"`) on a usable response. `confidence`
    is `None` when there was no triage; otherwise the overall 0-1 signal
    (mean of the check-level `items` confidences). `items` maps item ids --
    `{run_id}:{surface}:{check}`, always addressing a real check in the
    payload -- to their 0-1 confidence. `reason` is `None` on success and
    names the degrade cause (unset key, refused URL, transport failure,
    oversized/malformed response) otherwise.
    """

    mode: str
    confidence: float | None
    items: dict[str, float]
    reason: str | None


# An injectable triage callable: a TriageRequest in, a Contig-owned
# TriageResult out. The default is `NullTriage`; tests inject fakes, and the
# wiring aspect threads this seam through run/verify sites (mirrors the
# Executor/Fetcher/Sleeper injectable pattern in runner.py).
Triage = Callable[[TriageRequest], TriageResult]


def NullTriage(req: TriageRequest) -> TriageResult:
    """The default seam: "no triage", touching nothing (no env, no network)."""
    return TriageResult(mode="null", confidence=None, items={}, reason=None)


# ---------------------------------------------------------------------------
# R6: the single whitelist declaration for the egress payload
# ---------------------------------------------------------------------------

# The only keys allowed to leave the machine, in one declaration (R6). The
# run section carries numeric QC metadata (task counts, failures, repair
# attempts), the verdict string rendered, and file metadata -- sizes and
# sha256 hashes only, never paths. The check section carries each check's
# numeric `value` and shape metadata, never its `message`.
PAYLOAD_WHITELIST: dict[str, frozenset[str]] = {
    "run": frozenset(
        {
            "run_id",  # opaque per-run id, never a sample identifier
            "assay",
            "pipeline",
            "task_counts",
            "failed_tasks",
            "repair_attempts",
            "verdict",  # only the rendered string
            "files",  # container, filtered to "file" keys below
        }
    ),
    "file": frozenset({"size", "sha256"}),  # never a path, never read bytes
    "check": frozenset(
        {"check", "kind", "status", "value", "expected_range"}
    ),
}

# Run metadata keys that are strictly numeric QC metrics; everything else in
# the whitelist is a verbatim string (or the "files" container).
_NUMERIC_RUN_KEYS: frozenset[str] = frozenset(
    {"task_counts", "failed_tasks", "repair_attempts"}
)


def _is_numeric(value: object) -> bool:
    """True for a finite int/float (booleans and NaN/inf are not metrics)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _filter_file(file_meta: object) -> dict | None:
    """Reduce one file metadata entry to sizes/hashes only, or None.

    A path-only file entry is not egressable (R6: never paths) and is
    dropped entirely; an entry whose `size`/`sha256` values are not usable
    is reduced to the usable subset.
    """
    if not isinstance(file_meta, dict):
        return None
    out: dict = {}
    size = file_meta.get("size")
    if _is_numeric(size):
        out["size"] = size
    sha256 = file_meta.get("sha256")
    if isinstance(sha256, str) and len(sha256) == 64:
        out["sha256"] = sha256
    return out or None


def _filter_expected_range(entry: object) -> dict | None:
    """Keep only the numeric part of an expected-range band, or None.

    Bands like {"min": 250, "max": 500} or {"fail_below": 0.9} are numeric
    metadata; any non-numeric leaf (labels, text, paths) is dropped. An
    empty band is dropped entirely so free-text can never ride along.
    """
    if not isinstance(entry, dict):
        return None
    out = {k: v for k, v in entry.items() if _is_numeric(v)}
    return out or None


def _filter_check(check: object) -> dict | None:
    """Reduce one check dict to the whitelisted shape metadata, or None."""
    if not isinstance(check, dict):
        return None
    out: dict = {}
    for key in ("check", "kind", "status"):
        value = check.get(key)
        if isinstance(value, str):
            out[key] = value
    value = check.get("value")
    if _is_numeric(value):
        out["value"] = value
    expected_range = _filter_expected_range(check.get("expected_range"))
    if expected_range is not None:
        out["expected_range"] = expected_range
    return out or None


def build_triage_payload(run_meta: dict, checks: list[dict]) -> dict:
    """Build the whitelisted egress payload from run metadata and checks.

    Only keys named in `PAYLOAD_WHITELIST` survive; every other key (paths,
    raw-read markers, sample identifiers, messages, keys) is dropped. Values
    are type-filtered: numeric keys hold finite numbers only, string keys
    hold the verbatim string (the `verdict` string rendered), file metadata
    is reduced to size/sha256 (never paths), and `expected_range` holds
    numeric leaves only. Returns `{"run": {...}, "checks": [...]}`.
    """
    run: dict = {}
    for key, value in run_meta.items():
        if key not in PAYLOAD_WHITELIST["run"]:
            continue
        if key == "files":
            files = [
                f for f in (_filter_file(f) for f in value) if f is not None
            ] if isinstance(value, list) else []
            if files:
                run["files"] = files
            continue
        if key in _NUMERIC_RUN_KEYS:
            if _is_numeric(value):
                run[key] = value
        elif isinstance(value, str):
            run[key] = value
    checks_out = [c for c in (_filter_check(c) for c in checks) if c is not None]
    return {"run": run, "checks": checks_out}


# ---------------------------------------------------------------------------
# R2/R7: env-gated https-only transport behind a _post_json seam
# ---------------------------------------------------------------------------

# BYOK gate (mirrors SIGNING_KEY_ENV in bundle.py): absent/empty ⇒ NullTriage
# behavior, no network, exit unchanged. The key is never logged and never
# included in any payload.
JEV_KEY_ENV = "CONTIG_JEV_KEY"

# The https base URL for the triage request; absent/empty ⇒ Null behavior.
# No hard-coded vendor URL: the Jev endpoint contract is unverified, so the
# URL is recorded here, not papered over.
JEV_URL_ENV = "CONTIG_JEV_URL"

# Manual live-gate opt-out: when set truthy, http://localhost URLs are
# accepted for the owner-run smoke test. Off by default; the payload carries
# a bearer key, so plain-http egress is refused everywhere else.
JEV_ALLOW_HTTP_ENV = "CONTIG_JEV_ALLOW_HTTP"

# A triage request that hangs must not hang a run/verify: strict timeout,
# mirroring _FETCH_TIMEOUT in paper_intake.py.
_TRIAGE_TIMEOUT = 30

# Response size bound: a pathological triage response is an honest give-up
# ("oversized"), never a read-hang or an unbounded buffer.
_MAX_TRIAGE_RESPONSE_BYTES = 64 * 1024


def _url_allowed(url: str) -> bool:
    """True when `url` is an https endpoint, or localhost behind the opt-out.

    Scheme parsing must not raise on garbage input: bad URLs simply refuse
    the triage (Null behavior). Never regex-only: `urllib.parse` decides.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if not parsed.hostname:
        return False
    if parsed.scheme == "https":
        return True
    if parsed.scheme == "http" and parsed.hostname == "localhost":
        return bool(os.environ.get(JEV_ALLOW_HTTP_ENV))
    return False


def _post_json(
    url: str,
    payload: dict,
    *,
    timeout: int = _TRIAGE_TIMEOUT,
    max_bytes: int = _MAX_TRIAGE_RESPONSE_BYTES,
) -> str | None:
    """POST `payload` (a JSON object) to `url`; return the raw reply text.

    The only network touch point of this module; tests patch it (and, for
    the transport itself, the module-level `urllib.request.urlopen`). Never
    raises: connection errors, HTTP errors and timeouts all return None (the
    caller degrades to Null behavior). The reply is read size-bounded so a
    pathological response cannot hang the caller.
    """
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    except Exception:
        return None
    return body.decode("utf-8", errors="replace")


def _null_result(reason: str) -> TriageResult:
    """The shared degrade: mode="null", no triage signal, reason named."""
    return TriageResult(mode="null", confidence=None, items={}, reason=reason)


def parse_triage_response(text: str, *, known_ids: set[str]) -> dict[str, float] | None:
    """Parse a Contig-owned triage reply into `{item_id: confidence}`.

    The reply shape is `{"items": [{"id": ..., "confidence": 0-1}]}`. A
    request is only usable as a whole (dict with a list `items`); anything
    else — malformed JSON, non-dict, missing/ non-list `items` — returns None
    (Null behavior). Item-level problems never raise: ids unknown to the
    payload are dropped (an item always addresses a real check), and
    confidence values outside [0, 1], or non-numeric, are dropped.
    """
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    raw_items = obj.get("items")
    if not isinstance(raw_items, list):
        return None
    items: dict[str, float] = {}
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("id")
        confidence = entry.get("confidence")
        if not isinstance(item_id, str) or item_id not in known_ids:
            continue
        if isinstance(confidence, bool) or not isinstance(
            confidence, (int, float)
        ):
            continue
        if not math.isfinite(confidence) or not (0.0 <= confidence <= 1.0):
            continue
        items[item_id] = float(confidence)
    return items


def default_jev_triage(req: TriageRequest) -> TriageResult:
    """The real seam: env-gated, https-only POST, defensively parsed.

    Every failure mode degrades to the Null behavior (never raises, never
    changes caller behavior): key absent/empty ⇒ no request constructed at
    all; URL absent/empty or refused ⇒ no request; transport failure,
    oversized or malformed reply ⇒ Null with the reason named. On success
    the result carries the request's mode and the parsed check-level
    confidences (ids `{run_id}:{surface}:{check}`); `confidence` is the mean
    of the check-level confidences.
    """
    if not os.environ.get(JEV_KEY_ENV):
        return _null_result(f"{JEV_KEY_ENV} is not set; triage disabled")
    url = os.environ.get(JEV_URL_ENV)
    if not url:
        return _null_result(f"{JEV_URL_ENV} is not set; triage disabled")
    if not _url_allowed(url):
        return _null_result(f"refusing non-https triage URL {url!r}")
    try:
        text = _post_json(
            url,
            req.payload,
            timeout=_TRIAGE_TIMEOUT,
            max_bytes=_MAX_TRIAGE_RESPONSE_BYTES,
        )
    except Exception:
        text = None
    if text is None:
        return _null_result("triage request failed")
    if len(text.encode("utf-8", errors="replace")) > _MAX_TRIAGE_RESPONSE_BYTES:
        return _null_result(
            "triage response oversized (exceeds "
            f"{_MAX_TRIAGE_RESPONSE_BYTES} bytes)"
        )
    check_names = [
        check["check"]
        for check in req.payload.get("checks", [])
        if isinstance(check, dict) and isinstance(check.get("check"), str)
    ]
    known_ids = {f"{req.run_id}:{req.surface}:{name}" for name in check_names}
    items = parse_triage_response(text, known_ids=known_ids)
    if items is None:
        return _null_result("malformed triage response")
    confidence = sum(items.values()) / len(items) if items else None
    return TriageResult(
        mode=req.mode, confidence=confidence, items=items, reason=None
    )


def triage_for(
    mode_requested: bool, threshold: float | None
) -> tuple[Triage, str]:
    """The env-derived seam + mode string for the wiring sites.

    The single construction point of the seam the run/verify paths hand to the
    wrap sites: absent/empty `CONTIG_JEV_KEY` gives `(NullTriage, "null")` (no
    triage, no ledger rows); a key present gives `default_jev_triage`, in
    `"shadow"` mode by default, and `"active"` when `mode_requested`
    (`--triage-active`). The mode string feeds `TriageRequest.mode`
    (shadow/active) and the ledger row's `mode` field. `threshold` is the
    caller's 0-1 confidence budget for the active-mode skip decision; it does
    not influence which seam or mode is selected.
    """
    if not os.environ.get(JEV_KEY_ENV):
        return NullTriage, "null"
    if mode_requested:
        return default_jev_triage, "active"
    return default_jev_triage, "shadow"


# ---------------------------------------------------------------------------
# Wiring helpers: the R4 skip predicate and the R8 calibration ledger writer
# ---------------------------------------------------------------------------

# The band keys a rule declares (rule_pack.py `_status_for`); a `fail_*` key
# means the rule can FAIL a verdict, so no active-mode triage may skip it (R4).
_BAND_KEYS = ("warn_below", "warn_above", "fail_below", "fail_above")
_FAIL_BAND_PREFIX = "fail_"


def is_skippable_check(kind: str, bands: "Mapping[str, object] | None") -> bool:
    """The R4 predicate: may an active-mode triage skip this check?

    True iff `kind == "concordance"` (cross-tool corroboration is at-most-WARN,
    so skipping it can never change a verdict) or `bands` is present (not
    None) with no `fail_*` key among the rule's band keys
    (`warn_below`/`warn_above`/`fail_below`/`fail_above`). A FAIL-capable rule
    (`ts_tv`, `het_hom`, `variant_count`, `somatic_variant_count`) or a
    band-less structural/did-it-run check is never skippable. Pinned by an
    enumeration test walking the shipped rule packs, so a future FAIL band
    joining a skippable rule is a deliberate act.
    """
    if kind == "concordance":
        return True
    if bands is None:
        return False
    return not any(key.startswith(_FAIL_BAND_PREFIX) for key in bands)


def append_ledger_row(runs_dir: str | os.PathLike, row: dict) -> None:
    """Append one row to `<runs_dir>/triage-ledger.jsonl` (R8, wiring-owned).

    The unsigned calibration sidecar: one line per triaged decision, consumed
    by `contig triage-stats` (ledger aspect). Append-only, `errors="replace"`,
    never raises: an unwritable path degrades silently, because a calibration
    ledger must never fail a run/verify.
    """
    if not row:
        return
    try:
        path = Path(runs_dir) / "triage-ledger.jsonl"
        Path(runs_dir).mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except (OSError, TypeError, ValueError):
        return