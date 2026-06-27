# self-heal-missing-index (real recovery from a missing/stale index)

Source: no GitHub issue. Inline brief, owner `aliz`, branch
`feat/self-heal-missing-index/aliz`. Origin: the explicitly-named next slice of
capability **C2** (self-heal breadth), `docs/technical/CAPABILITY_ROADMAP.md:94-132`,
called out as a later C2 slice in the resource-aware-retry PRD Out-of-Scope
(`docs/planning/resource-aware-retry/prd.md:186-188`). Picked by `contig-next` as
the highest-leverage unblocked feature after the resource-aware-retry slice closed.

## Brief

Make Contig's self-heal actually recover from a **missing or stale index** instead
of a no-op re-run. It is unblocked (unlike peak-RSS scaling, which needs a
`resource_usage` refactor).

### The gap

- `repair.py:56-64` already proposes a `kind="reference", operation={"build_index":
  True}` patch for the `missing_index` FailureClass.
- But `self_heal.py:293-295` notes a reference patch *without* `set_param` "stays
  re-run only (unchanged params)" — i.e. today the index is never built, so the
  retry just fails again the same way. The scaffolding (FailureClass + patch
  proposal) exists but the repair is hollow.

### What to build

- Implement the `build_index` operation in `apply_patch` (`self_heal.py`) as an
  **auxiliary prep action** — build/regenerate the missing index, then retry —
  rather than the config mutations the loop does today. (New patch *action shape*:
  running a command, not mutating config.)
- Confirm `detect.py` actually emits the `missing_index` FailureClass from real log
  signatures; seed a corpus case for it.
- Keep it deterministic and CI-safe behind the injected `Executor` (no real
  tool/Nextflow runs), test-first, mirroring `tests/test_self_heal.py`.

## Why it is the moat

Raises the headline reliability metric — unattended-completion rate
(`CAPABILITY_ROADMAP.md:110-111`). Each recovered mode seeds a golden corpus case
(moat #2), and the diagnosis path gets better as base models improve. Incumbents do
mechanical resubmit only; none builds the missing artifact and retries. Stays
entirely Layer 2 (run + self-heal), never Layer 1.

## The caveat (nearest feasibility risk)

`build_index` is currently a no-op re-run (`self_heal.py:293-295`). Making it real
introduces a new patch *action shape* (run a command to build the index before
retry), unlike the existing config-mutation patches. Need to decide which indices,
and how to build them in a tool-agnostic, injectable, CI-safe way. Must confirm
`detect.py` classifies `missing_index` from real log signatures.

## Scope guardrails (CLAUDE.md / FEATURES.md)

- No raw-read egress; the index build runs on the user's compute.
- Self-heal stays bounded and logged; reuse the existing `max_attempts` bound.
- Test-first; no real pipeline/tool execution in tests (inject fakes per the
  existing `Executor` seam in `runner.py`).

## Open questions for the interview

- Which indices are in scope (FASTA `.fai`, BWA/STAR index, `.dict`, tabix `.tbi`,
  BAM `.bai`)? Start with one, or a small declared set?
- How is the index built — a tool command via the `Executor`, or by letting the
  pipeline regenerate it (e.g. clearing a stale index / flipping a param)? The
  former is a new action shape; the latter may reuse the existing config-mutation
  path.
- "Missing" vs "stale": is stale-index detection in scope, or only fully-missing?
- How is the build command resolved without raw tool execution in tests — a typed
  build step the injected `Executor` fulfils?
- What does the seeded corpus case look like (log signature → `missing_index`)?
- Does anything need to surface in the report/verdict, or is `repair_history` +
  JSONL the whole footprint this slice (mirroring the resource-aware-retry slice)?
