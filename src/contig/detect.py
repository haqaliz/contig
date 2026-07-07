"""Rule-based failure detection for a FAILED run (ARCHITECTURE §5.1).

`diagnose_failure` classifies a failed Nextflow run from its terminal task
events plus the captured error-log text. Rules are matched in priority order;
the first match wins. The result is a structured `Diagnosis` carrying the
matching evidence and a confidence the self-healing loop can act on.
"""

from __future__ import annotations

import json
import os
from typing import Callable, get_args

from contig.models import Diagnosis, FailureClass, TaskEvent

# A Detector is any callable that maps a failed run's terminal events plus its
# captured log text to a Diagnosis (PRD contract C). diagnose_failure is the
# default rules detector; a future LLM detector plugs in behind this same type.
Detector = Callable[[list[TaskEvent], str], Diagnosis]


def _matching_lines(log_text: str, needles: tuple[str, ...]) -> list[str]:
    """Log lines (original-case) containing any needle, matched case-insensitively."""
    hits = []
    for line in log_text.splitlines():
        low = line.lower()
        if any(n in low for n in needles):
            hits.append(line.strip())
    return hits


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    """True if any needle appears in text, matched case-insensitively."""
    low = text.lower()
    return any(n in low for n in needles)


def diagnose_failure(events: list[TaskEvent], log_text: str) -> Diagnosis:
    # OOM wins outright: an exit-137 kill is unambiguous even if the log also
    # carries a generic error, so it is checked before any log-text rule.
    oom_exit = any(e.exit == 137 for e in events)
    oom_lines = _matching_lines(
        log_text, ("out of memory", "outofmemoryerror", "killed", "oom")
    )
    if oom_exit or oom_lines:
        evidence = (["exit 137"] if oom_exit else []) + oom_lines
        return Diagnosis(
            failure_class="oom",
            root_cause="Process ran out of memory.",
            evidence=evidence,
            confidence=0.9,
        )

    time_lines = _matching_lines(
        log_text, ("due to time limit", "term_runlimit", "time limit")
    )
    if time_lines:
        return Diagnosis(
            failure_class="time_limit",
            root_cause="Run exceeded its wall-clock time limit.",
            evidence=time_lines,
            confidence=0.9,
        )

    # Disk exhaustion is unambiguous and resource-shaped: a full work/scratch
    # volume aborts the task. Checked early so it beats the generic crash rule.
    disk_lines = _matching_lines(
        log_text, ("no space left on device", "enospc", "disk quota exceeded")
    )
    if disk_lines:
        return Diagnosis(
            failure_class="disk_full",
            root_cause="The run ran out of disk space.",
            evidence=disk_lines,
            confidence=0.9,
        )

    # A filesystem permission problem (publishing outputs, writing scratch): a
    # human must fix the path/ownership; retrying on the same host will not help.
    perm_lines = _matching_lines(log_text, ("permission denied", "eacces"))
    if perm_lines:
        return Diagnosis(
            failure_class="permission_denied",
            root_cause="A filesystem permission denied the run access.",
            evidence=perm_lines,
            confidence=0.85,
        )

    unavailable_lines = _matching_lines(
        log_text,
        (
            "docker desktop is unable to start",
            "cannot connect to the docker daemon",
            "docker.sock",
        ),
    )
    if unavailable_lines:
        return Diagnosis(
            failure_class="container_unavailable",
            root_cause="Container runtime (Docker daemon) is not available.",
            evidence=unavailable_lines,
            confidence=0.9,
        )

    pull_lines = _matching_lines(
        log_text,
        (
            "failed to pull",
            "manifest unknown",
            "pull access denied",
            "error response from daemon: pull",
        ),
    )
    if pull_lines:
        return Diagnosis(
            failure_class="container_pull_failed",
            root_cause="Container image could not be pulled.",
            evidence=pull_lines,
            confidence=0.9,
        )

    # Staging / network download of a remote input or reference failed. Often
    # transient (a retry is the fix). Checked after the container-pull rule so an
    # image pull is not misread as a generic download.
    download_lines = _matching_lines(
        log_text,
        (
            "failed to download",
            "unable to stage",
            "error staging",
            "connection timed out",
            "connection reset by peer",
            "temporary failure in name resolution",
        ),
    )
    if download_lines:
        return Diagnosis(
            failure_class="download_failed",
            root_cause="A remote input or reference could not be downloaded.",
            evidence=download_lines,
            confidence=0.85,
        )

    conda_lines = _matching_lines(
        log_text, ("resolvepackagenotfound", "packagesnotfounderror")
    )
    low = log_text.lower()
    if "conda" in low and "solve" in low:
        conda_lines = conda_lines or _matching_lines(log_text, ("conda", "solve"))
    if conda_lines:
        return Diagnosis(
            failure_class="conda_solve_failed",
            root_cause="Conda environment could not be solved.",
            evidence=conda_lines,
            confidence=0.9,
        )

    notfound_lines = _matching_lines(
        log_text, ("not found", "missing", "no such file")
    )
    # Require the index/.fai to appear ON a "not found"/"missing"/"no such file"
    # line. A bare .fai mention is noise (e.g. `samtools faidx` naming its own
    # successful output genome.fasta.fai), and must not trigger missing_index.
    index_lines = [
        line
        for line in notfound_lines
        if ("index" in line.lower() or _has_any(line, (".fai", ".bai", ".tbi", ".csi")))
    ]
    if index_lines:
        return Diagnosis(
            failure_class="missing_index",
            root_cause="A required index file is missing.",
            evidence=index_lines,
            confidence=0.85,
        )

    # GATK reports a missing sequence dictionary as "Fasta dict file ... does not
    # exist", and "does not exist" is deliberately NOT in the first-stage notfound
    # tuple above (adding it there would over-trigger). So we need a targeted branch.
    # It stays NARROW on purpose: a line must carry BOTH a .dict token AND an
    # absence phrase. A wrong-reference / contig-mismatch line mentions .fasta or
    # "reference" but no absence phrase, so it is left for that different (deferred)
    # failure class rather than being swallowed here.
    dict_absent = [
        line
        for line in _matching_lines(
            log_text, ("does not exist", "not found", "no such file", "missing")
        )
        if _has_any(line, (".dict",))
    ]
    if dict_absent:
        return Diagnosis(
            failure_class="missing_index",
            root_cause="A required sequence dictionary is missing.",
            evidence=dict_absent,
            confidence=0.85,
        )

    # STAR opens genomeParameters.txt first, so an absent/partial genome index
    # surfaces as this exact FATAL ERROR line. Gated on the STAR-specific
    # filename / phrase so it stays narrow (mirrors the .dict branch above).
    star_missing_lines = _matching_lines(
        log_text, ("genomeparameters.txt", "could not open genome file")
    )
    if star_missing_lines:
        return Diagnosis(
            failure_class="missing_index",
            root_cause="STAR's genome index is missing or was not fully built.",
            evidence=star_missing_lines,
            confidence=0.85,
        )

    # STAR refuses to load a genome index built by an incompatible STAR
    # version. Narrow on purpose: a line must carry BOTH "Genome version" AND
    # "INCOMPATIBLE", so a generic version mention elsewhere is not swallowed.
    star_version_lines = [
        line
        for line in _matching_lines(log_text, ("genome version",))
        if _has_any(line, ("incompatible",))
    ]
    if star_version_lines:
        return Diagnosis(
            failure_class="missing_index",
            root_cause="STAR's genome index was built with an incompatible STAR version.",
            evidence=star_version_lines,
            confidence=0.85,
        )

    # Classic bwa's index loader reports a missing index this way. Narrow on
    # purpose: a line must carry BOTH the loader's function name AND the
    # "fail to locate the index" phrase.
    bwa_missing_lines = [
        line
        for line in _matching_lines(log_text, ("bwa_idx_load_from_disk",))
        if _has_any(line, ("fail to locate the index",))
    ]
    if bwa_missing_lines:
        return Diagnosis(
            failure_class="missing_index",
            root_cause="BWA's index files could not be located.",
            evidence=bwa_missing_lines,
            confidence=0.85,
        )

    # bwa-mem2's index loader (FMI_search.cpp) prints this exact line then
    # exit(EXIT_FAILURE) when a sidecar is missing/truncated/version-incompatible.
    # The message is generic ("Unable to open the file"), so gate on the
    # bwa-mem2-only sidecar token `.bwt.2bit.64` to stay narrow: a wrong-reference
    # line carries neither token, and classic bwa keeps its own branch above.
    bwamem2_missing_lines = [
        line
        for line in _matching_lines(log_text, ("unable to open the file",))
        if _has_any(line, ("bwt.2bit.64",))
    ]
    if bwamem2_missing_lines:
        return Diagnosis(
            failure_class="missing_index",
            root_cause="bwa-mem2's index is missing, incomplete, or incompatible.",
            evidence=bwamem2_missing_lines,
            confidence=0.85,
        )

    nosuchfile_lines = _matching_lines(log_text, ("no such file or directory",))
    ref_tokens = (".fasta", ".fa", ".gtf", ".gff", "reference", "genome")
    ref_lines = [line for line in nosuchfile_lines if _has_any(line, ref_tokens)]
    if ref_lines:
        return Diagnosis(
            failure_class="missing_reference",
            root_cause="A required reference file is missing.",
            evidence=ref_lines,
            confidence=0.85,
        )

    param_lines = _matching_lines(
        log_text,
        (
            "unknown option",
            "unrecognized arguments",
            "unexpected argument",
            "is not a valid parameter",
            # nf-core's parameter-schema validation banner (seen on real runs):
            # an invalid/missing --param value is a parameter problem, not a crash.
            "validation of pipeline parameters failed",
            "invalid input values have been detected",
            "schemavalidationexception",
        ),
    )
    if param_lines:
        return Diagnosis(
            failure_class="bad_param",
            root_cause="A pipeline parameter or tool option is invalid.",
            evidence=param_lines,
            confidence=0.85,
        )

    # Apple-Silicon-style architecture mismatch: nf-core's amd64-only containers
    # run under emulation, and a step gets KILLED (no exit code). The platform
    # warning alone is noise (it appears on healthy tasks too), so we require it
    # together with a killed (exit-less) failure.
    platform_lines = _matching_lines(
        log_text,
        (
            "does not match the detected host platform",
            "requested image's platform",
            "no matching manifest for",
        ),
    )
    if platform_lines and any(e.is_failure and e.exit is None for e in events):
        return Diagnosis(
            failure_class="platform_unsupported",
            root_cause=(
                "A pipeline step's container has no image for this host's CPU "
                "architecture; it ran under emulation and was killed."
            ),
            evidence=platform_lines,
            confidence=0.7,
        )

    # samtools faidx refuses a plain-gzip'd (non-BGZF) reference FASTA. Narrow
    # on purpose: anchor on the faidx-specific "cannot index files compressed
    # with gzip" phrase, NOT the bare "please use bgzip" -- tabix/bcftools
    # emit that same trailing phrase for VCFs, a different fix entirely.
    bgzf_lines = _matching_lines(
        log_text, ("cannot index files compressed with gzip",)
    )
    if bgzf_lines:
        fai_lines = _matching_lines(log_text, ("could not build fai index",))
        return Diagnosis(
            failure_class="reference_not_bgzf",
            root_cause=(
                "Reference FASTA is gzip-compressed, not BGZF; samtools faidx "
                "cannot index it."
            ),
            evidence=bgzf_lines + fai_lines,
            confidence=0.85,
        )

    # No specific signal matched. If a task did fail, the tool itself crashed
    # for a reason we could not classify; otherwise we have nothing to go on.
    if any(e.is_failure for e in events):
        crash_lines = [
            line for line in log_text.splitlines() if line.strip()
        ][-1:]
        return Diagnosis(
            failure_class="tool_crash",
            root_cause="A task failed with an unrecognized error.",
            evidence=crash_lines,
            confidence=0.4,
        )

    return Diagnosis(
        failure_class="unknown",
        root_cause="No matching failure signal.",
        confidence=0.2,
    )


# --- strict (higher-precision) detector ----------------------------------------
# Same rules, but it refuses to name a specific class when the evidence is weak.
# On weak evidence it prefers tool_crash (a task did fail) or unknown (nothing
# failed) over a confident-sounding guess. This trades recall for precision.

# The two weak-evidence verdicts the default detector can reach:
#   platform_unsupported: rests on a warning that appears on healthy tasks too,
#       so a co-occurring kill is suggestive, not conclusive (confidence 0.7).
#   conda_solve_failed via the loose heuristic: a bare "conda" line plus a bare
#       "solve" line anywhere in the log, with neither strong needle present.
# When the default lands on one of these by weak evidence, strict steps back.

_CONDA_STRONG_NEEDLES = ("resolvepackagenotfound", "packagesnotfounderror")


def diagnose_failure_strict(events: list[TaskEvent], log_text: str) -> Diagnosis:
    """Higher-precision detector: demote weak-evidence guesses (PRD contract C).

    Runs the same rules, then steps back from the two classes the default
    detector reaches on weak evidence (platform_unsupported, and conda_solve_failed
    matched only by the loose "conda"+"solve" heuristic). On a failed task it
    reports tool_crash; with no failure it reports unknown.
    """
    base = diagnose_failure(events, log_text)

    weak = False
    if base.failure_class == "platform_unsupported":
        weak = True
    elif base.failure_class == "conda_solve_failed" and not _has_any(
        log_text, _CONDA_STRONG_NEEDLES
    ):
        weak = True

    if not weak:
        return base

    if any(e.is_failure for e in events):
        crash_lines = [line for line in log_text.splitlines() if line.strip()][-1:]
        return Diagnosis(
            failure_class="tool_crash",
            root_cause="A task failed; evidence too weak to name a specific cause.",
            evidence=crash_lines,
            confidence=0.4,
        )
    return Diagnosis(
        failure_class="unknown",
        root_cause="No conclusive failure signal.",
        confidence=0.2,
    )


# --- provider-agnostic LLM detector (PRD contract A) ---------------------------
# An OPTIONAL detector behind the same Detector type. It is gated by env: it
# registers only when a provider AND its key are configured, so the default
# suite never imports a provider SDK or hits the network. The provider call is
# isolated behind `_llm_complete`, a tiny seam tests monkeypatch with a fake.

# Provider -> the env var holding its API key. CONTIG_LLM_PROVIDER selects one.
_LLM_PROVIDER_KEY_ENV: dict[str, str] = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# The valid FailureClass labels, derived from the model so the prompt and the
# fallback stay in sync with the schema (no hand-maintained second list).
_VALID_FAILURE_CLASSES: frozenset[str] = frozenset(get_args(FailureClass))


def _selected_provider() -> str | None:
    """The configured provider whose key is present, or None if not usable.

    Returns None when CONTIG_LLM_PROVIDER is unset, names an unknown provider, or
    the matching key env is empty. This is the single env gate; it never reads or
    returns the key value itself.
    """
    provider = os.environ.get("CONTIG_LLM_PROVIDER")
    if provider is None:
        return None
    provider = provider.strip().lower()
    key_env = _LLM_PROVIDER_KEY_ENV.get(provider)
    if key_env is None:
        return None
    if not os.environ.get(key_env):
        return None
    return provider


def llm_detector_available() -> bool:
    """Whether the LLM detector can be built from the current environment."""
    return _selected_provider() is not None


def _missing_llm_env_message() -> str:
    """A clear, secret-free explanation of what env the LLM detector needs."""
    provider = os.environ.get("CONTIG_LLM_PROVIDER")
    if provider is None:
        return (
            "the 'llm' detector needs CONTIG_LLM_PROVIDER set to 'claude' or "
            "'openai' (with the matching ANTHROPIC_API_KEY or OPENAI_API_KEY)"
        )
    provider_norm = provider.strip().lower()
    key_env = _LLM_PROVIDER_KEY_ENV.get(provider_norm)
    if key_env is None:
        known = ", ".join(sorted(_LLM_PROVIDER_KEY_ENV))
        return (
            f"the 'llm' detector got unknown CONTIG_LLM_PROVIDER {provider!r}; "
            f"known providers: {known}"
        )
    return f"the 'llm' detector needs {key_env} set for provider {provider_norm!r}"


def _llm_complete(provider: str, prompt: str) -> str:
    """Send one prompt to the selected provider and return the raw text reply.

    This is the ONLY place a provider SDK is imported (lazily) or the network is
    touched, so the whole detector is mocked by monkeypatching this one function.
    The API key is read from env here and never logged or returned.
    """
    key_env = _LLM_PROVIDER_KEY_ENV[provider]
    api_key = os.environ[key_env]
    if provider == "claude":
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
    # openai
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content or ""


def _build_prompt(events: list[TaskEvent], log_text: str) -> str:
    """One prompt asking for a strict JSON diagnosis (FailureClass + cause + conf)."""
    classes = ", ".join(sorted(_VALID_FAILURE_CLASSES))
    event_lines = "\n".join(
        f"- process={e.process} status={e.status} exit={e.exit}" for e in events
    )
    return (
        "You are a bioinformatics pipeline failure classifier. Given a failed "
        "Nextflow run's terminal task events and its captured error log, classify "
        "the root cause.\n\n"
        f"Reply with ONLY a JSON object: {{\"failure_class\": one of [{classes}], "
        '"root_cause": a short sentence, "confidence": a number from 0.0 to 1.0}}.\n\n'
        f"Terminal task events:\n{event_lines or '(none)'}\n\n"
        f"Error log:\n{log_text}\n"
    )


def _extract_json_object(text: str) -> dict | None:
    """Parse the first top-level JSON object out of a model reply, or None.

    Tolerates JSON wrapped in prose by taking the substring from the first '{'
    to the last '}'. Returns None when nothing parseable is found.
    """
    stripped = text.strip()
    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _diagnosis_from_reply(reply: str) -> Diagnosis:
    """Map a raw model reply to a Diagnosis, falling back to unknown on any gap."""
    obj = _extract_json_object(reply)
    if obj is None:
        return Diagnosis(
            failure_class="unknown",
            root_cause="LLM detector could not parse a diagnosis from the response.",
            confidence=0.2,
        )
    failure_class = obj.get("failure_class")
    if failure_class not in _VALID_FAILURE_CLASSES:
        return Diagnosis(
            failure_class="unknown",
            root_cause="LLM detector returned an unrecognized failure class.",
            confidence=0.2,
        )
    root_cause = str(obj.get("root_cause") or "LLM detector diagnosis.")
    try:
        confidence = float(obj.get("confidence", 0.5))
    except (ValueError, TypeError):
        confidence = 0.5
    confidence = min(1.0, max(0.0, confidence))
    return Diagnosis(
        failure_class=failure_class, root_cause=root_cause, confidence=confidence
    )


def build_llm_detector() -> Detector:
    """Build the LLM Detector closure (PRD contract A); requires configured env.

    Raises KeyError (naming the missing env) when no provider/key is configured,
    so callers get the same clear error get_detector gives. The returned callable
    maps (events, log_text) to a Diagnosis via one prompt and never raises: any
    provider or parse error falls back to an unknown Diagnosis.
    """
    provider = _selected_provider()
    if provider is None:
        raise KeyError(_missing_llm_env_message())

    def detect_with_llm(events: list[TaskEvent], log_text: str) -> Diagnosis:
        prompt = _build_prompt(events, log_text)
        try:
            reply = _llm_complete(provider, prompt)
        except Exception:
            # A provider/network error must not crash the self-heal loop; we
            # degrade to unknown so a rules detector can still act. The exception
            # is intentionally not logged (it can carry request context).
            return Diagnosis(
                failure_class="unknown",
                root_cause="LLM detector could not reach the provider.",
                confidence=0.2,
            )
        return _diagnosis_from_reply(reply)

    return detect_with_llm


# Registry of named detectors (PRD contract C). The orchestrator resolves a CLI
# flag through get_detector; the corpus eval scores any value here. The static
# map holds only the always-available, network-free rules detectors; "llm" is
# resolved dynamically (and only when its env is configured) so importing this
# module never pulls in a provider SDK or touches the network.
DETECTORS: dict[str, Detector] = {
    "rules": diagnose_failure,
    "rules-strict": diagnose_failure_strict,
}


def available_detectors() -> list[str]:
    """Names resolvable right now: the static rules plus 'llm' when configured."""
    names = list(DETECTORS)
    if llm_detector_available():
        names.append("llm")
    return names


def get_detector(name: str) -> Detector:
    """Resolve a detector by name; an unknown name is a clear KeyError.

    "llm" is resolved through the env-gated builder: when no provider/key is
    configured it raises a KeyError naming the missing env, so the optional
    detector fails loudly instead of silently classifying nothing.
    """
    if name == "llm":
        return build_llm_detector()
    try:
        return DETECTORS[name]
    except KeyError:
        available = ", ".join(sorted(available_detectors()))
        raise KeyError(
            f"unknown detector {name!r}; available detectors: {available}"
        ) from None
