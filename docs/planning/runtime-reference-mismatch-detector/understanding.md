# Understanding — runtime-reference-mismatch-detector

Phase 2 dig note. Grounded in the Phase 1 card (`docs/planning/_card/issue.md`) and a
graphify-first code map (verified file:line citations inline).

## What the work is really asking

Seed the **runtime half** of the reference-integrity family: a new
`reference_mismatch` `FailureClass` literal (19 → 20) plus a narrow AND-guarded
branch in the runtime failure detector (`diagnose_failure`) that recognizes
**hard-fail** log signatures of a wrong reference — aligner fatal errors on reads
whose contigs are absent from the reference (e.g. STAR "Contig 'X' not found in
the reference dictionary", bwa/HISAT2 "not found in reference" family, GATK
"incompatible contigs"). Today every one of those classifies `tool_crash` at
confidence 0.4 (`src/contig/detect.py:434-445`, verified empirically). The slice
is detector+corpus only: no repair exists or is proposed (the honest give-up
pattern, `propose_patches` returns `[]` for classes without a branch,
`src/contig/repair.py:14-183`), matching the `alignment_format_mismatch`
precedent.

The pre-flight side of this family is shipped (v0.7.0 contig-naming refusal,
chr-prefix harmonization, per-contig alias harmonization); every one of those
slices explicitly recorded "no new `reference_mismatch` `FailureClass` or
detector-corpus case" (CHANGELOG:2968, :3282) and the C2 deferral list still
carries "a runtime `reference_mismatch` detector-corpus case"
(CAPABILITY_ROADMAP.md:512-516). This slice closes that deferral.

## Affected areas (all paths relative to the worktree root)

- `src/contig/models.py:262-282` — `FailureClass` Literal, 19 members today; add
  `"reference_mismatch"`. Literal is the single source of truth; the detector's
  valid set is derived (`detect.py:519`). No signature break (precedent
  `tests/test_signing.py:218-289`).
- `src/contig/detect.py` — new branch after `alignment_format_mismatch`
  (`:414-432`) and before `tool_crash` (`:434`), AND-guarded, confidence 0.85.
  The missing_index branches already decline this family on purpose
  (`:249-251`, `:316-317`), and the two existing negative tests
  (`tests/test_detect.py:272-284`, `:331-337`) assert `!= missing_index` for
  exactly these logs — they become positive `reference_mismatch` coverage.
- `src/contig/data/detector_corpus.jsonl` — one golden case (27 → 28; the
  training-corpus guard `tests/test_corpus.py:146-153` must stay 100%).
- `src/contig/data/detector_corpus_holdout.jsonl` — one independently authored
  holdout twin (14 → 15; `holdout-` id, `source: holdout:synthetic`, pinned by
  `tests/test_eval_holdout.py:47-92`); `holdout_baseline.json` refrozen via
  `contig eval-guard --update-baseline` (92.9% → 14/15 if it classifies;
  otherwise a disclosed known-miss). Twin-authoring precedent:
  `cram-reference-required` (htslib wording) / `holdout-cram-reference-required`
  (GATK wording), pinned by `tests/test_eval_holdout.py:75-84`.
- `src/contig/data/heal_scenarios.jsonl` — one give-up scenario (22 → 23),
  near-clone of `alignment-format-mismatch-give-up` (line 22);
  `covered_classes` 16 → 17; `tests/test_heal_scenarios.py:791-817` updated;
  `heal_baseline.json` refrozen via `contig heal-guard --update-baseline`
  (outcome-match must stay 1.0).
- Dashboard sync: `dashboard/lib/derive.ts:278-298` (FAILURE_CLASSES mirror),
  `dashboard/e2e/failure-classes.spec.ts:26-59` (the 19-length pin), promote
  route `dashboard/app/api/corpus/promote/route.ts:28` (auto-accepts via the
  mirror). Note `dashboard/components/run/repair-timeline.tsx:25` already carries
  a `reference_mismatch` display label ("Reference mismatch").
- `src/contig/cli.py:3079-3118` — the heal-guard docstring is **already stale**
  ("15 covered classes", "3 of the 18 literals"; actual 16 of 19); fix in this
  slice.

## Non-overlap with `qc_anomaly` (structural, verified)

`qc_anomaly` fires only in the **success** path (`self_heal.py:1233-1302`):
`RunSummary.succeeded` AND non-empty `qc_results` AND `overall_verdict == fail`,
synthesized in place at confidence 1.0 — it never reaches `diagnose_failure` and
never sees a hard-fail log (a succeeded run has no stderr). The new branch lives
in the **exception** path (`diagnose_failure`, called from `self_heal.py:1311`) on
FAILED task events. No double-classification is possible; the design guard is
simply that the branch keys on hard-fail signatures, so a wrong-reference run
that completes green and fails QC stays `qc_anomaly`.

## Ambiguities / open questions for the interview

1. **Needle set**: which exact AND-guards — the STAR "not found in the reference
   dictionary/genome" family vs bwa/HISAT2 "not found in reference" vs GATK
   "incompatible contigs"? How narrow is narrow (the family's standing rule: the
   needle must not over-match `missing_index`/`missing_reference`, which are
   anchored on absence/index phrases)?
2. **Naming**: `reference_mismatch` shares its Python name with the pre-flight
   `--allow-reference-mismatch` flag and `LaunchManifest.allow_reference_mismatch`
   (`cli.py:406`, `models.py:434`) — a different layer, no functional collision;
   confirm the literal name is the roadmap's own wording.
3. **Holdout twin framing**: the second author should use a different tool's
   wording (the `cram-reference-required` precedent used GATK vs htslib).
4. **Golden case + controls**: the standard negative controls (same-family
   logs that must NOT classify — e.g. genuine `missing_index`/`missing_reference`
   text, and the existing dict-branch control).
5. **heal-guard**: confirm the give-up scenario ships in this slice (moves
   covered_classes 16 → 17) rather than deferring it.
6. **Dashboard**: e2e `failure-classes.spec.ts` length pin and `PYTHON_ORDER`
   update, plus the stale heal-guard docstring fix — in scope or follow-on?

## Contradiction surfaced (not papered over)

The v0.9.0-era decision was "provenance-only capture, no corpus case"
(CHANGELOG:2968) — but the C2 deferral list written since then still names the
runtime case as pending work (CAPABILITY_ROADMAP.md:512-516), and the
understanding for the harmonization work recorded the runtime seeding as the open
"moat-vs-architecture question" (`docs/planning/self-heal-reference-mismatch/understanding.md`
update note). The roadmap is authoritative: this slice is sanctioned, not a
re-recommendation of a blocker-deferred item. The assembly-signature pre-flight
form and the C5 known-sites/GTF-version slices remain blocked/out of scope and
are not touched.

## Guardrails check (CLAUDE.md)

Layer 2 (detection/self-heal) ✓. No raw-read egress ✓. No correctness over-claim
(the detector names the failure; the honest give-up means no false repair) ✓.
Test-first, synthetic fixtures, no nf-core in CI ✓. Not Layer 1 ✓. Not
blocker-deferred work ✓.