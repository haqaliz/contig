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
`default_jev_triage` POSTs the REAL Jev systemone envelope -- `{model,
state, questions}` with ONE `triage` score question whose ordered
`criteria` array has EXACTLY two levels (level0 clean, level1 suspicious),
so the returned score lies in [0, 1] by construction -- over stdlib
`urllib` to the pinned `DEFAULT_JEV_ENDPOINT`
(`https://api.typesafe.ai/v1/systemone`) unless `CONTIG_JEV_URL` overrides
it, with the key in `Authorization: Bearer <key>`, a strict
`_TRIAGE_TIMEOUT = 30` s timeout, and a size-bound
`_MAX_TRIAGE_RESPONSE_BYTES = 64 KiB` response. The endpoint must be
`https://` (the payload rides a bearer key): a non-https URL is refused by
the seam, except `http://localhost` for the manual live gate behind the
explicit `CONTIG_JEV_ALLOW_HTTP` opt-out (off by default). `CONTIG_JEV_MODEL`
names the full model id; aliases are refused (not reproducible policy). The
real reply `{"answers": {"triage": {"type": "score", "score": 0-1,
"confidence": 0-1}}, "usage": ...}` is parsed fail-closed by
`parse_triage_response` into `(score, confidence)` -- a declined
(`{"error": ...}`), malformed, or out-of-range reply is Null behavior,
never a guessed value.

Degrade-to-Null contract:
key absent/empty ⇒ no request constructed at all (asserted); model
absent/blank or an alias ⇒ no request; a refused URL ⇒ no request (absent
URL ⇒ the pinned default endpoint); a state carrying a key the whitelist
does not name ⇒ no egress; transport failure, timeout, HTTP error,
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
    is `None` when there was no triage; otherwise the reply's
    `answers.triage.confidence` (0-1). `items` maps the one score item --
    id `{run_id}:{surface}:triage` -- to the reply's `answers.triage.score`
    (0-1); a score is never guessed from a shape the contract does not name.
    `reason` is `None` on success and names the degrade cause (unset key or
    model, alias model, refused URL, non-whitelisted payload, transport
    failure, oversized/malformed response) otherwise.
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

# The https base URL for the triage request; absent/blank ⇒ the pinned
# `DEFAULT_JEV_ENDPOINT` is used -- the REAL Jev systemone protocol URL
# (verified live 2026-09-22 by the sibling Belay integration). Never a
# guessed endpoint.
JEV_URL_ENV = "CONTIG_JEV_URL"

# The env var naming the full model id (e.g. `jev-1.13.0`). Absent/blank ⇒
# Null behavior naming the env; aliases are refused (a short alias would pin
# the reply to whatever the vendor's alias table says on the operator's box,
# which is not reproducible policy -- the Belay D-2 precedent).
JEV_MODEL_ENV = "CONTIG_JEV_MODEL"

# The pinned default Jev systemone endpoint (see `JEV_URL_ENV`).
DEFAULT_JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"

# Model id aliases. Full ids only — an alias is not reproducible policy.
_MODEL_ALIASES = frozenset({"jev", "system-one"})

# The single score question's name in the `questions` envelope.
_QUESTION_NAME = "triage"

# The score question's Contig-scoped instructions: how likely THIS run's QC
# anomalies are worth an expensive deep check. Higher = more worth running.
_QUESTION_INSTRUCTIONS = (
    "Score how likely this run's QC anomalies are worth an expensive deep "
    "check. The `state` is a JSON object of whitelisted QC metrics and "
    "metadata for one run: task counts, repair attempts, the rendered "
    "verdict, file sizes/hashes, and each failed or anomalous check's "
    "numeric value and shape metadata. A higher score means the run is MORE "
    "likely to warrant a deep corroboration pass (an expensive re-check of "
    "the suspicious anomaly)."
)

# The ordered level descriptions. Exactly TWO levels, ordered from clean
# (level 0) to suspicious (level 1), so the returned score lies in [0, 1]
# by construction.
_QUESTION_CRITERIA = [
    "The run looks clean: nothing in the QC metrics suggests the anomaly is worth a deep check.",
    "The run looks suspicious: the QC metrics suggest the anomaly is worth a deep check.",
]

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


def _build_systemone_request(model: str, state: dict) -> dict:
    """The real Jev systemone request envelope for one score question.

    `state` is the whitelisted egress payload; `questions` holds exactly ONE
    score question named `triage` whose ordered `criteria` array has exactly
    two levels (level0 clean, level1 suspicious), so the returned score lies
    in [0, 1] by construction. Pure: no env, no IO.
    """
    return {
        "model": model,
        "state": state,
        "questions": {
            _QUESTION_NAME: {
                "type": "score",
                "instructions": _QUESTION_INSTRUCTIONS,
                "criteria": list(_QUESTION_CRITERIA),
            }
        },
    }


def _state_keys_whitelisted(state: object) -> bool:
    """True iff every section of `state` carries only whitelisted keys.

    Defense in depth before egress: the state must be the payload shape
    (`run`/`checks` sections, `files` entries under `run`) whose keys all
    come from `PAYLOAD_WHITELIST`. A hand-built or drifted state carrying any
    key the whitelist does not name is refused, so the transport is never
    called with it.
    """
    if not isinstance(state, dict):
        return False
    if set(state) - {"run", "checks"}:
        return False
    run = state.get("run")
    if run is not None and (
        not isinstance(run, dict) or set(run) - PAYLOAD_WHITELIST["run"]
    ):
        return False
    checks = state.get("checks")
    if checks is not None and not isinstance(checks, list):
        return False
    if isinstance(checks, list):
        for check in checks:
            if (
                not isinstance(check, dict)
                or set(check) - PAYLOAD_WHITELIST["check"]
            ):
                return False
    if isinstance(run, dict):
        files = run.get("files")
        if files is not None and not isinstance(files, list):
            return False
        if isinstance(files, list):
            for file_meta in files:
                if (
                    not isinstance(file_meta, dict)
                    or set(file_meta) - PAYLOAD_WHITELIST["file"]
                ):
                    return False
    return True


def _post_json(
    url: str,
    payload: dict,
    *,
    timeout: int = _TRIAGE_TIMEOUT,
    max_bytes: int = _MAX_TRIAGE_RESPONSE_BYTES,
    key: str,
) -> str | None:
    """POST `payload` (a JSON object) to `url`; return the raw reply text.

    The key rides in `Authorization: Bearer <key>` (never in the body); the
    payload rides as JSON with `Content-Type: application/json`. The only
    network touch point of this module; tests patch it (and, for the
    transport itself, the module-level `urllib.request.urlopen`). Never
    raises: connection errors, HTTP errors and timeouts all return None (the
    caller degrades to Null behavior). The reply is read size-bounded so a
    pathological response cannot hang the caller.
    """
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
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


def parse_triage_response(text: str) -> tuple[float, float] | None:
    """Parse the real systemone reply into `(score, confidence)`, or None.

    The reply shape is `{"answers": {"triage": {"type": "score", "score":
    0-1, "confidence": 0-1}}, "usage": ...}`. None (Null behavior, a score is
    never guessed) for: malformed JSON, a non-dict reply, `{"error": ...}`
    (the endpoint's decline), a missing or non-object `answers` or
    `answers.triage`, or a boolean/non-numeric/out-of-[0,1] `score` or
    `confidence`.
    """
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    if "error" in obj:
        return None
    answers = obj.get("answers")
    if not isinstance(answers, dict):
        return None
    answer = answers.get(_QUESTION_NAME)
    if not isinstance(answer, dict):
        return None
    score = answer.get("score")
    confidence = answer.get("confidence")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    if not math.isfinite(score) or not (0.0 <= score <= 1.0):
        return None
    if not math.isfinite(confidence) or not (0.0 <= confidence <= 1.0):
        return None
    return (float(score), float(confidence))


def default_jev_triage(req: TriageRequest) -> TriageResult:
    """The real seam: env-gated, https-only POST, fail-closed parse.

    Every failure mode degrades to the Null behavior (never raises, never
    changes caller behavior): key absent/empty ⇒ no request constructed at
    all; model absent/blank or an alias ⇒ no request; a refused URL ⇒ no
    request (absent URL ⇒ the pinned `DEFAULT_JEV_ENDPOINT`); a payload
    carrying a key the whitelist does not name ⇒ no egress; transport
    failure, oversized or malformed reply ⇒ Null with the reason named. On
    success the result carries the request's mode, the reply's
    `answers.triage.confidence`, and the one score item
    `{run_id}:{surface}:triage` mapped to the reply's score.
    """
    key = os.environ.get(JEV_KEY_ENV)
    if not key:
        return _null_result(f"{JEV_KEY_ENV} is not set; triage disabled")
    model = (os.environ.get(JEV_MODEL_ENV) or "").strip()
    if not model:
        return _null_result(f"{JEV_MODEL_ENV} is not set; triage disabled")
    if model in _MODEL_ALIASES:
        return _null_result(
            f"model id {model!r} is an alias; {JEV_MODEL_ENV} must name a "
            "full model id (aliases are not reproducible policy)"
        )
    url = (os.environ.get(JEV_URL_ENV) or "").strip() or DEFAULT_JEV_ENDPOINT
    if not _url_allowed(url):
        return _null_result(f"refusing non-https triage URL {url!r}")
    if not _state_keys_whitelisted(req.payload):
        return _null_result(
            "payload carries key(s) outside the whitelist; refusing egress"
        )
    try:
        text = _post_json(
            url,
            _build_systemone_request(model, req.payload),
            timeout=_TRIAGE_TIMEOUT,
            max_bytes=_MAX_TRIAGE_RESPONSE_BYTES,
            key=key,
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
    parsed = parse_triage_response(text)
    if parsed is None:
        return _null_result("malformed triage response")
    score, confidence = parsed
    return TriageResult(
        mode=req.mode,
        confidence=confidence,
        items={f"{req.run_id}:{req.surface}:{_QUESTION_NAME}": score},
        reason=None,
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


# ---------------------------------------------------------------------------
# Ledger aspect: the tolerant reader and the pure stats report
# ---------------------------------------------------------------------------


def load_triage_ledger(runs_dir: str | os.PathLike) -> tuple[list[dict], int]:
    """Read every row of `<runs_dir>/triage-ledger.jsonl`, tolerantly.

    Returns `(rows, skipped)`: the parsed rows in file order, and the count
    of lines that were not usable. A missing file is an absent ledger
    (`([], 0)`) -- never an error, matching the run/verify paths that would
    have written it. A malformed line, a line that parses to something other
    than a JSON object, or a non-UTF-8 line is skipped and counted, never
    raised: `snapshot_history`-style tolerance, because the ledger is user
    data and one bad line must not blind the report to the rest.

    An existing-but-unreadable file (permission, not-a-file, ...) raises
    `OSError` -- that is a caller-visible finding, not an absence -- so
    `contig triage-stats` can exit non-zero with an honest error instead of
    reporting an empty ledger.
    """
    path = Path(runs_dir) / "triage-ledger.jsonl"
    try:
        with open(path, "rb") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return [], 0
    rows: list[dict] = []
    skipped = 0
    for line in lines:
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError:
            skipped += 1
            continue
        try:
            obj = json.loads(text)
        except (ValueError, TypeError):
            skipped += 1
            continue
        if not isinstance(obj, dict):
            skipped += 1
            continue
        rows.append(obj)
    return rows, skipped


def triage_stats_report(rows: list[dict], *, skipped_lines: int = 0) -> dict:
    """Counts over ledger rows, as a plain deterministic dict (R8).

    Pure and rendered by somebody else (repair-stats' `repair_stats_report`
    precedent). Counts `total` rows, buckets by the `surface`/`mode` strings
    the rows actually carry, counts active-mode skip events (rows whose
    `actual` is exactly `"skipped"`), and carries the loader's
    `skipped_lines` tolerance count so the JSON shape stays stable even when
    the ledger is absent.

    `confidence_vs_actual` is a cross-tab, never a calibration claim:
    buckets are keyed by `actual`, each carries its own explicit `rows`
    denominator, and rows participate only when they carry a finite numeric
    `confidence` and a string `actual`. The table states how many rows it is
    built on (the sum of the bucket `rows`); a table over zero or one keyed
    run is explicitly not a curve, and the CLI says so.
    """
    by_surface: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    skipped = 0
    cross: dict[str, list[float]] = {}
    for row in rows:
        surface = row.get("surface")
        if isinstance(surface, str):
            by_surface[surface] = by_surface.get(surface, 0) + 1
        mode = row.get("mode")
        if isinstance(mode, str):
            by_mode[mode] = by_mode.get(mode, 0) + 1
        actual = row.get("actual")
        if actual == "skipped":
            skipped += 1
        confidence = row.get("confidence")
        if _is_numeric(confidence) and isinstance(actual, str):
            cross.setdefault(actual, []).append(float(confidence))
    confidence_vs_actual = [
        {
            "actual": actual,
            "rows": len(values),
            "mean_confidence": sum(values) / len(values),
        }
        for actual, values in sorted(cross.items())
    ]
    return {
        "total": len(rows),
        "by_surface": dict(sorted(by_surface.items())),
        "by_mode": dict(sorted(by_mode.items())),
        "skipped": skipped,
        "skipped_lines": skipped_lines,
        "confidence_vs_actual": confidence_vs_actual,
    }