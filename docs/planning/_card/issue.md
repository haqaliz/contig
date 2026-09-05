# Card: feat/auto-approve-attendance/aliz

**Source:** inline brief (no GitHub issue — `id` is a slug). Tracker probe:
`gh issue list` shows one open issue, #33 (flaky reproduce freshness guard),
unrelated to this work.

**Owner:** aliz · **Branch:** `feat/auto-approve-attendance/aliz`

---

## Brief

Persist whether a human was in the loop so `contig repair-stats` stops reporting
`attendance_unknown`.

Today `--auto-approve` (`src/contig/cli.py:414`) is never persisted anywhere in the
bundle, so the two self-heal outcome literals `approved_and_retried` and
`chose_and_retried` (recorded at `src/contig/self_heal.py:1379,1442`) are ambiguous:
each fires on a genuine human approval **and** under `--auto-approve`, where the
engine decides per policy and no human is involved. `src/contig/repair_stats.py:88-96`
correctly refuses to guess and files both literals into `ATTENDANCE_UNKNOWN_OUTCOMES`,
which leaves **both sides** of the unattended-completion rate unmeasurable.

That rate is the Phase 1 → Phase 2 exit gate: "≥70% unattended completion on the core
pipeline" (`docs/ROADMAP.md:109`). `contig repair-stats` shipped in v0.57.0 to compute
it, and filed this gap against itself:

> **Filed, not fixed:** a run record cannot say whether a human was in the loop, because
> `auto_approve` is captured nowhere in the bundle. Persisting it (on `LaunchManifest` or
> `ExecutionTarget`) would empty the `attendance_unknown` bucket and is the natural
> follow-on; it is a model/signature change and this slice is read-only by design.
> — `CHANGELOG.md:82-86`

## The first question (decide before implementing)

Where the field lives is a real trade-off, not a detail:

- **`LaunchManifest`** (`src/contig/models.py:411`) — precedent exists at
  `models.py:432-435` (`allow_reference_mismatch: bool = False`, with the legacy
  back-compat comment), written at `cli.py:769-790`. **No signature break** (signing
  covers `RunRecord` only, `src/contig/signing.py:55`). **But** `launch.json` is a
  *replay* surface: `rerun`/`reproduce` rebuild the invocation from it, so persisting
  attendance there means a replay silently inherits an unattended policy. That is the
  same objection that kept `--detect-stalls`/`--stall-timeout` deliberately off the
  manifest ("a stall is a property of the machine, not the analysis", `FEATURES.md:251`).
- **`RunRecord`** (`src/contig/models.py:325`) — semantically right: a fact about what
  happened, not an instruction for what to do again. **But** it is the signed payload
  (`signing.py:55` `canonical_record_bytes`), making this the **fifth** disclosed
  signature break, after C8 slice 6, C8 slice 8, the somatic FAIL floor, and
  `patch_applied`.
- A third option worth pricing: `ExecutionTarget` (`models.py:30`), which is nested
  *inside* `RunRecord` — so it carries the signature cost without the semantic win, and
  "was a human at the keyboard" is not a property of where the run executes.

## Scope

- Persist the attendance fact at launch.
- Thread it into the `repair_stats` attendance axis so `approved_and_retried` /
  `chose_and_retried` resolve to attended vs unattended when the fact is present.
- Legacy bundles (no field) must stay `attendance_unknown` — never defaulted into a
  state the record does not assert.

## Honest limits to carry into the writeup

- The existing 15 real bundles are a **frozen** record set, so the reported 64.3%
  (9/14 scored runs) does **not** move retroactively — only future runs get attendance.
- **Push, not demand-pull:** no design partner asked for this. It makes the self-heal
  loop's field performance legible; it recovers nothing for a user.

## Guardrail check

Layer 2 (run / self-heal / verify / reproduce) — this is provenance + eval
instrumentation on the self-heal loop. No Layer 1, no wet-lab/clinical dependency.
