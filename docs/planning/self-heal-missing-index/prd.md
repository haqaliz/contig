# PRD: Self-heal a missing index (build it, then retry)

**Slug:** `self-heal-missing-index` · **Branch:** `feat/self-heal-missing-index/aliz` ·
**Owner:** aliz
**Origin:** The explicitly-named next slice of capability **C2** (self-heal breadth),
`docs/technical/CAPABILITY_ROADMAP.md:94-132`; called out as a later C2 slice in the
resource-aware-retry PRD Out-of-Scope (`docs/planning/resource-aware-retry/prd.md:186-188`).
Selected by `contig-next` as the highest-leverage *unblocked* feature after the
resource-aware-retry slice closed (peak-RSS scaling, the other C2 item, is blocked
on a `resource_usage` refactor).

---

## Problem Statement

When a pipeline process fails because a **required index file is missing**, Contig
*detects* and *diagnoses* it correctly but **cannot recover it**. The repair is
hollow:

- Detection works: `detect.py:159-176` emits `failure_class="missing_index"`
  (confidence 0.85) when a log line contains `not found` / `missing` / `no such
  file` AND (`index` or one of `.fai .bai .tbi .csi`). Covered by
  `tests/test_detect.py::test_missing_fai_is_missing_index`.
- A patch is proposed: `repair.py:56-65` returns
  `Patch(kind="reference", operation={"build_index": True},
  risk="needs_confirmation", expected_signal="index present")`.
- **But applying it does nothing.** `apply_patch` (`self_heal.py:274-330`) only acts
  on a `reference` patch when it carries `set_param`; a `build_index` patch has none,
  so target/params are returned unchanged and the re-run is identical — and fails
  the same way. The code comment at ~293-295 states this, and
  `tests/test_self_heal.py::test_apply_patch_reference_build_index_is_rerun_only`
  asserts the no-op.

So a missing-index failure burns the retry budget and ends in an honest FAIL that a
human must fix manually — exactly the toil C2 exists to remove.

**Evidence it's real.** `missing_index` is one of the modeled `FailureClass` values
(`models.py:182-199`) and ships with a detector rule and test, i.e. it is a failure
the engine already expects to see. Unattended-completion rate is the Phase-1
headline reliability metric (`ROADMAP.md`, `CAPABILITY_ROADMAP.md:110-111`);
incumbents only do mechanical resubmit — none builds the missing artifact and
retries (`FEATURES.md` competitive scan).

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| A missing `.fai` is recovered autonomously | A test injecting "fail with missing `.fai`, then succeed once the index exists" heals to a PASS/WARN verdict with no human step (auto-approve), via an injected index-builder fake. |
| The build is a real, auditable repair step | `repair_history` records a `RepairStep` with `outcome="built_index_and_retried"`, the diagnosis, and the patch; the step is appended to `repair_progress.jsonl`. |
| A failed build gives up honestly | When the index build itself fails (builder returns non-zero), the loop stops with a distinct outcome (`index_build_failed`) and an honest FAIL — **never a false PASS**; the case is still captured to the pending corpus. |
| CI stays tool-free and deterministic | All tests inject a fake `IndexBuilder` (and the existing fake `Executor`); no real `samtools`/Nextflow/network runs. |
| The corpus compounds (moat #2) | One golden `missing_index` case is seeded into `src/contig/data/detector_corpus.jsonl`; the detector eval still passes. |

This is reliability/quality hardening, not a growth metric; success is the tests
above passing and the existing self-heal/detector suites staying green.

---

## User Personas & Scenarios

- **Persona A (lone computational biologist)** runs a germline analysis unattended
  overnight. An alignment/variant step fails because the reference FASTA has no
  `.fai`. Contig diagnoses `missing_index`, runs `samtools faidx ref.fasta`, retries,
  and the morning verdict shows the reasoned "built the index, then re-ran" chain
  instead of a dead run.
- **Persona A, the hard case:** the index build itself fails (e.g. the FASTA is
  truncated). Contig reports "index build failed for ref.fasta.fai" and stops with an
  honest FAIL, so the biologist knows exactly what broke — not "it broke."
- **Core facility (C):** wants throughput and auditable recovery; the built-index
  repair step in the provenance trail is exactly the kind of evidence a non-expert PI
  can trust.

---

## Requirements

### Must-have

- **M1 — Real index build on `missing_index`.** On a `missing_index` diagnosis whose
  `build_index` patch is applied, the loop derives the missing index path from
  `diagnosis.evidence`, builds it, and retries the **same** pipeline argv. Scope this
  slice to a **missing FASTA index (`.fai`)** built with `samtools faidx <fasta>`
  (the source FASTA is the evidence path with the trailing `.fai` removed).
- **M2 — A new injected `IndexBuilder` seam.** Building runs through a new seam
  mirroring the `Executor` pattern (`runner.py:72`,
  `Callable[[list[str], Path], int]`): a default implementation that shells out, and
  a fake injected in tests. `self_heal_run` gains an `index_builder` parameter with a
  shelling-out default. **No real tool runs in CI.**
- **M3 — Build happens at the loop level, not in `apply_patch`.** `apply_patch` stays
  pure (returns target/params); the index build is a side-effecting loop step invoked
  when the `build_index` patch is applied (both the `--auto-approve` and the
  human-approved gated paths, since the patch is `needs_confirmation`). The existing
  `test_apply_patch_reference_build_index_is_rerun_only` therefore remains valid; its
  comment (`self_heal.py:293-295`) is updated to point at the loop-level builder.
- **M4 — Honest outcome vocabulary + control flow.** Success records
  `RepairStep.outcome="built_index_and_retried"` and `continue`s to the next attempt.
  A non-zero builder result records `outcome="index_build_failed"` with a
  `RepairStep.detail` naming the index path and **`return _finalize(...)` (an honest
  FAIL) — it must NOT `continue`** into another retry. If the index path cannot be
  parsed from the evidence, record `outcome="index_unresolvable"` and finalize FAIL
  rather than guessing a build target. Never a false PASS. (Mirrors the
  resource-aware-retry slice's `gave_up_at_ceiling` pattern, `self_heal.py:540-546`,
  `models.py:225-233`.)
- **M4a — One shared apply-and-build helper.** Because `build_index` is
  `needs_confirmation` (gated), it is applied at more than one gated site in
  `self_heal_run` (the `auto_approve` branch ~`self_heal.py:443-451` and the
  unambiguous-approve branch ~`507-516`; the ambiguous branch ~470-480 too if it ever
  applies). The build + its success/failure outcome MUST be factored into a single
  helper invoked at each gated-apply site, so every path behaves identically. Do not
  inline the build at one site only.
- **M5 — Bounded.** The repair is bounded by the existing `max_attempts`; a build is
  attempted at most once per missing-index path, so a build that "succeeds" but
  leaves the failure unresolved cannot loop the builder (it still terminates within
  `max_attempts`).
- **M6 — Corpus capture + golden seed.** The pending-corpus capture on failure
  (`self_heal.py:399-409`) continues to label the case `missing_index`. One golden
  `missing_index` case is seeded into `src/contig/data/detector_corpus.jsonl`, and the
  detector eval (`tests/test_detect.py` and any corpus eval test) stays green.

### Should-have

- **S1 — Path parsing is robust to absolute and relative evidence paths.** Extract
  the `*.fai` token from the evidence line(s); derive the FASTA by stripping `.fai`;
  run the builder with the run/work dir as cwd.
- **S2 — The patch's `expected_signal` ("index present") is reflected** in the
  recorded step so the repair chain reads as a coherent detect→build→retry story.

### Nice-to-have (explicitly deferred — see Out of Scope)

- Other index kinds (`.bai` via `samtools index`, `.tbi/.csi` via `tabix`, `.dict`
  via `gatk`, STAR/BWA indexes) — a path-extension→command table is the natural
  extension point, left as follow-on cases.
- Letting the pipeline regenerate the index by clearing a stale index param
  (config-mutation route).
- Stale-index detection (present but older than source).

---

## Technical Considerations

**Insertion point.** The build is a loop step in `self_heal_run`
(`self_heal.py:333-554`), invoked where a chosen patch is applied — both the
auto-approve branch and the human-approved gated branch (the `build_index` patch is
`needs_confirmation`, so it never flows through the *safe*-patch path). Concretely:
when the applied patch is a `kind="reference"` patch with
`operation.get("build_index")`, call the `IndexBuilder` before the next
`run_pipeline` iteration; branch the recorded outcome on the builder's exit code.

**The seam.** New `IndexBuilder = Callable[[list[str], Path], int]` (argv, cwd →
exit code), default shells out via `subprocess` like `default_executor`
(`runner.py:88-99`). Threaded through `self_heal_run` as
`index_builder: IndexBuilder = default_index_builder`. The fake in tests creates the
`.fai` file (or returns non-zero to exercise the failure path).

**Path derivation.** Parse the missing index path from `diagnosis.evidence`
(the detector already collects the offending lines), take the `*.fai` token, and
build the FASTA target by removing the `.fai` suffix. Argv:
`["samtools", "faidx", "<fasta>"]`.

**Risk tier unchanged.** The `build_index` patch stays `needs_confirmation`
(`repair.py:60`). Building writes a file to the user's filesystem, so it remains
gated; the builder runs only after approval / `--auto-approve`. No risk-tier change
this slice.

**Reproducibility/verification impact.** No change to verdict-reduction guarantees:
an unrecovered run is FAIL, as today; the near-zero false-pass guarantee is
preserved. The build step is recorded in `repair_history` and the bundle, which
*strengthens* the auditable trail (a reader sees exactly what index was built and
how). No raw-read egress — the build runs on the user's compute.

**Testing.** Strict TDD with the injected `Executor` (`runner.py:72`) and the new
`IndexBuilder`. A fake executor returns missing-index failure on attempt 1; the fake
index-builder creates the `.fai` and returns 0; attempt 2 succeeds. A second test has
the builder return non-zero to assert `index_build_failed` + FAIL. Mirrors
`tests/test_self_heal.py` patterns (`_failing_then_capturing`, the
`gave_up_at_ceiling` test).

---

## Data Model / Contracts

- New seam type: `IndexBuilder = Callable[[list[str], Path], int]` (in `runner.py`,
  beside `Executor`).
- `self_heal_run` gains `index_builder: IndexBuilder = default_index_builder`.
- New `RepairStep.outcome` vocabulary values: `built_index_and_retried` and
  `index_build_failed` (free-form `outcome: str`; no model change required, mirroring
  `gave_up_at_ceiling`). `detail` carries the index path on failure.
- No change to `Patch`, `FailureClass`, or `apply_patch`'s return contract.
- Golden corpus gains one `FailureCase` with `expected_class="missing_index"`
  (`models.py:314-323`) in `src/contig/data/detector_corpus.jsonl`.

---

## Risks & Open Questions

- **R1 — Evidence path parsing.** Evidence lines vary by tool; the `.fai`-token
  extraction must handle the known `samtools`/`fai_load` message and degrade safely
  (if no path can be parsed, do not attempt a build — record an honest give-up rather
  than guessing). Cover with a test.
- **R2 — cwd / path resolution.** A relative index path depends on the process cwd.
  For the slice, run the builder with the run/work dir as cwd and pass the parsed path
  through; revisit if real runs show path mismatches.
- **R3 — Re-proposal loop.** A build that returns 0 but does not actually resolve the
  failure must not re-trigger the builder indefinitely. Mitigation: at most one build
  per missing-index path, plus the existing `max_attempts` bound. Cover with a
  termination test.
- **R4 — Dashboard surface.** Rendering the new outcomes in the dashboard repair
  chain is **out of scope** (data lands in `repair_history`/JSONL; rendering is a
  follow-on), matching the resource-aware-retry slice's choice.
- **R5 — `-resume` interaction.** A retried attempt runs with Nextflow `-resume`
  (`self_heal.py:385`). After building the index, the re-run must actually re-execute
  the previously-failed process (not skip it from cache). The injected fake executor
  controls this in tests; a test should assert attempt 2 re-runs and succeeds once the
  `.fai` exists.
- **R6 — Interactive gate + failed build.** Under an interactive (non-`--auto-approve`)
  gate, the build runs only after the human approves; if it then fails, the run ends
  FAIL with no second gate. Whether a failed build should re-enter the gate with an
  alternative is **out of scope** this slice (one approve→build→retry is the ceiling);
  flagged as the open question below.

---

## Out of Scope (explicit)

- **Other index kinds** (`.bai`, `.tbi/.csi`, `.dict`, STAR/BWA) — follow-on cases on
  the same seam.
- **Pipeline-regenerate (config-mutation) route** for self-buildable indexes.
- **Stale-index detection** (present-but-older-than-source). Detection changes are out
  of scope; `detect.py`'s `missing_index` rule is unchanged.
- **Risk-tier change** for the `build_index` patch (stays `needs_confirmation`).
- **Dashboard rendering** of the new outcomes.

---

## Guardrails check (CLAUDE.md)

Layer 2 only (run + self-heal); no Layer-1 workflow authoring. No raw-read egress —
the index build runs on the user's compute. Self-heal stays bounded (`max_attempts`)
and logged. Gets better as base models improve — a smarter diagnoser still flows
through the same bounded build-and-retry repair. Test-first; no real tool/Nextflow
execution in tests.
