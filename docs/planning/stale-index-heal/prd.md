# PRD: Stale-Index Self-Heal

**Slug:** `stale-index-heal`  ·  **Branch:** `feat/stale-index-heal/aliz`  ·  **Owner:** aliz
**Status:** Draft for review gate · **Capability:** C2 (self-heal breadth), slice of the missing-index family

---

## Problem Statement

A user supplies a reference (or alignment data) plus its index files. If an index was
built from an **older version** of the data it indexes — a reference updated between
runs, an index copied from an old project, a hand-rolled index next to a freshly
downloaded FASTA — htslib refuses to use it: `[E::hts_idx_load3] The index file is
older than the data file: X`.

Today this failure is **undiagnosed**: the message carries no absence phrase
("not found"/"missing"/"no such file"), so every shipped `missing_index` branch in
`detect.py` misses it and it falls through to a plain `tool_crash` with no repair.
The run fails on the user's compute, a human rebuilds the index by hand, and the
attempt is wasted. The inverse misdiagnosis exists too: a message that combines
absence with staleness wording ("... is missing or older than the data file") is
**swallowed by the generic missing-index branch** (`detect.py:211-222`) and triggers a
rebuild attempt of an index that already exists — the repair would be aimed at the
wrong artifact.

**Evidence it's real:** the htslib message family is real third-party output (htslib's
`hts_idx_load3`), and the stale-index class is a classic shared-HPC failure ("update
reference, forget to rebuild index"). **Honest limit:** no real Contig-launched run has
ever been observed producing it — this is push, not demand-pull, exactly the disclosure
every C2 slice carries (the field corpus has only ever diagnosed `oom`, `tool_crash`,
`missing_index`, `unknown`; CHANGELOG v0.50.0).

**What we are NOT building (named, so the slice stays honest):** the wrong-reference
index flavor (index built against a *different* reference — the mtime check cannot
distinguish it; see Risks), `.dict` staleness (GATK warns, doesn't hard-fail — no
confirmed anchor), and a pre-flight stat-based freshness guard (the engine does not
know implicit-lookup index paths before the pipeline runs).

---

## Goals & Success Metrics

| Goal | Success metric |
|---|---|
| A stale single-file index is detected, rebuilt from the run's resolved source, and the run retried — unattended, without a human | New detector branch classifies the seeded stale case; `built_index_and_retried` outcome with staleness evidence in `RepairStep.detail` |
| No regression anywhere in the shipped index machinery | Detector training suite stays 100%; `eval-guard` held-out accuracy **unmoved at 92.3% (12/13)**; `heal-guard` outcome-match **stays 1.0** (refrozen with the new scenario); no signature break |
| The class joins the compounding corpus (moat #2) | One golden training-corpus case + one `heal-guard` scenario seeded; baseline refrozen as a deliberate `--update-baseline` act |
| Test-first discipline | Every production change lands behind a failing test; injected executors/builder — no real nf-core run in CI |

**Metric honesty:** the guarded numbers move only if we deliberately refreeze; the
`eval-guard` holdout is untouched and must *not* move. `heal-guard` `covered_classes`
stays 11 — `missing_index` is already covered; this slice adds a scenario, not a class.

---

## User Personas & Scenarios

- **A, lone computational biologist**: updates their reference FASTA, forgets the
  `.fai`/`.bai`, reruns — today gets a cryptic htslib error and a wasted attempt.
- **C, core facility**: shared reference dirs get bumped; downstream users' runs fail
  with stale indexes. Contig's unattended repair is exactly the consistency they sell.
- **B, wet-lab scientist who cannot code**: sees the failure, cannot fix an index by
  hand. The self-heal (with the `needs_confirmation` gate) is the difference between a
  completed run and a support ticket.

---

## Requirements

### Must have (each testable)

- **M1 — Detector branch (new, narrow).** A branch in `detect.py` placed **before** the
  generic single-file `missing_index` branch (`detect.py:205-222`) and the `.dict`
  branch (`detect.py:231-237`), AND-guarded on a **freshness phrase** (`"older than"` —
  the htslib `hts_idx_load3` family) plus an index token (`.fai`/`.bai`/`.tbi`/`.csi`
  or the words "index file"). Emits `Diagnosis(failure_class="missing_index",
  confidence=0.85)` with the matching lines as evidence. Must **not** match absence
  phrasing (those stay with the generic branch) and must **not** steal the bwa-mem2 /
  classic-BWA / STAR branches. Every existing corpus case classifies unchanged.
- **M2 — Path parse.** The stale index path is extracted from the message (htslib names
  it: `The index file is older than the data file: X`). Unparseable/absent → honest
  `index_unresolvable`.
- **M3 — Rebuild with the shipped table.** Source = index path minus its suffix,
  dispatched through `_INDEX_BUILD` (`self_heal.py:194-200`) — `.fai` →
  `samtools faidx`, `.bai` → `samtools index`, `.tbi` → `tabix -p vcf`, `.csi` →
  `bcftools index`.
- **M4 — Scratch build + atomic replace (user decision).** Build into run-scoped
  scratch (`<run_id>/healed_index/<name>`, fresh-wiped, STAR-slice precedent
  `self_heal.py:683-687`); on a **successful** build, replace the stale sidecar
  atomically (`os.replace`). A failed build leaves the user's file untouched — the
  honest half of the mechanics. Same-`built_paths` build-once guard; give-ups:
  `index_unresolvable` / `index_build_failed` (never a false pass).
- **M5 — Record.** Reuse the `built_index_and_retried` outcome literal (dashboard
  `LIVE_OUTCOMES === 19` pin stays untouched). `RepairStep.detail` records the observed
  old/new mtimes, the freshness phrase, and the applied build argv. Patch stays
  `kind="reference"`, `risk="needs_confirmation"` (unchanged from `repair.py:56-65`).
- **M6 — Corpus + guard scenario.** One golden training-corpus case with a realistic
  htslib-shaped stale line that trips **only** the new branch (the
  `reference_not_bgzf` wording-sensitivity trap, `heal_scenarios.jsonl:11`, applies:
  reword toward "not found" and the line silently changes class). One `heal-guard`
  scenario (attempt 1 fails with the stale line → build succeeds → retried →
  `built_index_and_retried`, `expected_recovered: true`, `expected_patch_applied: true`).
  `heal_baseline.json` refrozen **in the same commit** as the scenario (`--update-baseline`,
  never a hand-edit); `heal_history.jsonl` appended.
- **M7 — Tests, RED first.** Detector: stale lines per kind classify; absence lines still
  hit the generic branch; mixed "missing or older" lines classify as stale (branch
  ordering pinned); holdout suite unmoved. Repair: scratch+replace pinned (success
  replaces, failure leaves the file byte-identical), build-once, give-ups, cross-device
  fallback (see R5). All via injected executors/builder — no real nf-core in CI.
- **M8 — Docs.** `CAPABILITY_ROADMAP.md` C2 record (stale-index slice shipped) and a
  CHANGELOG entry, written in the same commit wave as the code.

### Should have

- **S1** — One golden corpus case per kind (`.bai`/`.tbi`/`.csi`), mirroring how the
  missing-index family seeded one per kind; M6's single case is the minimum.
- **S2** — A `heal-guard` variant with a **failed build** (index rebuild fails → honest
  `index_build_failed` give-up, `expected_recovered: false`), proving the loop records
  the give-up honestly.

### Nice to have

- **N1** — `.dict` stale detection (deferred: no confirmed GATK hard-fail message to
  anchor on; revisit if one is observed in the field).
- **N2** — Recording the run's resolved reference identity (C5 `ReferenceIdentity`
  sha) into the repair detail, making a wrong-reference masquerade visible after the
  fact.

---

## Technical Considerations

- **Detector ordering is load-bearing.** The stale branch sits ahead of the generic
  `missing_index` branch; the needles are disjoint (freshness vs absence), pinned by
  tests in both directions. Any future absence-phrased stale message ("missing **or
  older**") classifies stale-first.
- **`samtools faidx` silently rebuilds a stale `.fai`** — the hard fail lives in the
  htslib `hts_idx_load3` family (`.bai`/`.csi`/`.tbi`). The `.fai` kind stays in the
  rebuild table (defensive: if any tool hard-fails on a stale `.fai` with freshness
  wording, it is caught); no work is claimed for the silent-rebuild path.
- **Scratch + atomic replace.** Scratch under `<run_id>/healed_index/` (STAR precedent).
  `os.replace` is atomic only within one filesystem — the run dir and the user's
  reference may be on different mounts. **Open question (decide in plan):** same-dir
  temp + rename fallback when `os.replace` raises `OSError(EXDEV)`, vs honest
  `index_build_failed` give-up. Recommendation: same-dir dot-prefixed temp
  (`<sidecar>.contig-heal.*`) then `os.replace` — same filesystem by construction.
- **Reproducibility contract.** No `LaunchManifest` change, no new model fields, no
  `canonical_record_bytes` change → **no signature break**. `rerun`/`resume` re-derive
  the heal from the original manifest fields (no scratch path persisted), matching the
  STAR/bgzip reproduce-safety contract.
- **Eval plumbing.** `eval-guard` holdout + baseline untouched (no new FailureClass);
  the plan must include a CI assertion that `eval-guard` reports 92.3% unchanged after
  the branch lands. `heal-guard` `corpus_sha` changes with the new scenario → refreeze
  in the same commit (the `patch_applied` slice's own discipline: correction and
  refreeze must land together or a real regression launders into the baseline).

---

## Data Model / Artifact / Run Contracts

- **Unchanged:** `FailureClass` (reuses `missing_index`), `Patch` shape
  (`operation={"build_index": True}`, `risk="needs_confirmation"`), outcome literal
  (reuses `built_index_and_retried`), `RunRecord`/`LaunchManifest`, signature payload,
  `RepairStep` schema (`detail` is already free-form).
- **Written:** `RepairStep.detail` with `{kind: "stale_index", old_mtime, new_mtime,
  phrase, argv}`; pending-corpus `FailureCase` append via the loop's existing path.

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Push, not demand-pull** — organic frequency unmeasured; no real stale-index run has been observed | Recorded in the roadmap entry and CHANGELOG as the standing disclosure; the slice ships as readiness (a taxonomy gap closes), not as measured field value |
| R2 | **Needle is reasoned, not observed** — htslib wording could drift across versions, or a foreign tool's text containing "older than" + an index token misclassifies | Keep the needle set minimal (`"older than"` + index token), keep the message-shape guard (the index-file naming form), seed a golden case; a non-matching stale message degrades to today's `tool_crash` — no regression |
| R3 | **Branch collision** — absence-phrased stale text swallowed by the generic `missing_index` branch, or the new branch stealing existing corpus cases | Branch ordering + disjoint needle families, pinned by tests in both directions; full corpus + holdout suites in CI |
| R4 | **Mutation of user data** — the repair overwrites a user-supplied index file | Scratch build first; the user's file is replaced only by a successful build, atomically; patch stays `needs_confirmation` (approval gate or `--auto-approve`), matching every shipped index patch; the overwritten file is derived data (rebuildable from the reference) |
| R5 | **Cross-device replace** (`os.replace` EXDEV) | Same-dir temp + rename fallback, or honest `index_build_failed` — decided in the plan (recommendation above) |
| R6 | **Refreeze coupling** — refreezing without the scenario, or the scenario without the refreeze, launders a regression into the baseline | Scenario + refreeze land in the same commit; corpus-level RED (scenario-count assertion, sha mismatch) is genuine per the catalog-coverage precedent |
| R7 | **Wrong-reference index masquerade** — the rebuild fixes the symptom while the run silently succeeds against the wrong reference | Named out of scope; N2 (reference-identity in detail) is the honest follow-on; the C2 assembly-signature mismatch detector remains the home for the flavor |

---

## Out of Scope

- Wrong-reference index flavor (different reference, not an older version of the same one)
- `.dict` stale detection (no confirmed hard-fail anchor)
- Directory-shaped indexes (STAR version-incompatible rebuild already shipped)
- Pre-flight stat-based freshness guard (engine can't enumerate implicit-lookup index paths)
- Classic-BWA / bwa-mem2 build-and-redirect (separate deferred C2 items, no live trigger)
- FAIL severity, exit-code changes, dashboard changes, new outcome literal, new FailureClass
- Any Layer-1 (NL→workflow) surface — this is purely the run/self-heal layer

---

## Guardrails Check (CLAUDE.md)

- **Layer 2 only:** detection + repair + retry on the shipped self-heal loop. ✓
- **Moat + eval data:** one more recovered failure mode and one more corpus case; better
  base models make the orchestrator better, never redundant. ✓
- **Founder's edge:** no credentials, no proprietary data, no regulatory surface. ✓
- **No over-claiming:** honest give-ups, no false pass, push-not-demand-pull disclosed. ✓
- **Test-first:** M7. ✓
