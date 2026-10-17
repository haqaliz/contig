# Understanding — star-index-corrupt-heal (C2 follow-on)

Phase-2 dig note. Source: `docs/planning/_card/issue.md` (inline brief, `/contig-next`
handoff 2026-10-17) plus a graphify-first code map. **No `graphify-out/` in this
worktree**, so the map was built by direct reads and three parallel explore agents
(all file:line citations verified inline below).

## What the work is really asking

Close C2 deferral **N1**: a corrupt/partial STAR genome index
(`FATAL GENOME INDEX FILE error: … is corrupt, or is incompatible`) currently
falls through the detector to `tool_crash` at confidence 0.4
(`src/contig/detect.py:456-465`), so the self-heal loop never diagnoses it and the
run ends in an honest but unhelpful FAIL. The slice makes the engine **detect** it
as `missing_index` and **heal** it by reusing the shipped STAR directory-index
rebuild+redirect (`_build_star_index`), landing a golden corpus case and a
heal-guard scenario. No new `FailureClass` — `missing_index` already exists
(`models.py:276`).

## Affected areas (verified)

- **Detector** `src/contig/detect.py`: the STAR branches sit at `:267-295` (missing
  keyed on `genomeparameters.txt`/`could not open genome file`; version-incompatible
  keyed on `genome version` + `incompatible`), all `missing_index` @0.85. The corrupt
  phrasing matches **neither**, nor the generic absence-anchored branches
  (`:213-243`), nor `missing_reference`/`reference_mismatch`. It reaches the
  `tool_crash` fallback at `:456-465`. New branch goes beside the other STAR branches,
  AND-guarded, before `tool_crash`.
- **Routing predicate — the load-bearing finding the brief under-stated.**
  Reaching the heal is **not** a detect.py-only change. `_parse_missing_index`
  (`src/contig/self_heal.py:126-155`) routes to `kind == "star"` only if a line
  passes `_is_star_signature` (`:113-123`), which today matches only
  `genomeparameters.txt` / `could not open genome file` / (`genome version` AND
  `incompatible`). The corrupt phrasing matches none → `_parse_missing_index` returns
  `None` → the loop gives up `index_unresolvable` (`self_heal.py:1115-1122`), never
  reaching `_build_star_index`. **So `_is_star_signature` must also match the corrupt
  phrasing**; the `_build_star_index` body itself is untouched.
- **The heal** `_build_star_index` (`self_heal.py:653-760`): needs `params["fasta"]`
  (`:697-705`) and a resolvable genomeDir — `parsed_path` from a
  `<dir>/genomeParameters.txt` token, else `params["star_index"]` (`:688`); writes a
  fresh `run_dir/healed_index/star` (`:714-718`), builds
  `STAR --runMode genomeGenerate …` (`:719-730`), redirects
  `params["star_index"]` to scratch (`:753`), returns `built_index_and_retried`
  (`:760`). Give-ups are honest (`index_unresolvable`/`index_build_failed`).
- **Patch** `propose_patches` (`repair.py:56-65`): `missing_index` → one
  `kind="reference"`, `operation={"build_index": True}`, **`risk="needs_confirmation"`**
  patch (gated). No STAR sub-cause branch exists — all three STAR flavours share it.
- **Corpus** `src/contig/data/detector_corpus.jsonl` (28 lines) and
  `detector_corpus_holdout.jsonl` (15 lines): `FailureCase` schema
  (`models.py:486-494`). Training-corpus guard: `tests/test_corpus.py:150-153`
  (`accuracy == 1.0`, no exact-size pin). Holdout baseline
  `src/contig/data/holdout_baseline.json` = 14/15 (0.933), `corpus_sha ac475206…`,
  refrozen via `contig eval-guard --update-baseline`.
- **Heal-guard** `src/contig/data/heal_scenarios.jsonl` (23) + `heal_baseline.json`
  (23, outcome-match 1.0, recovery 11/23, covered_classes 17). `HealScenario`
  (`models.py:587-635`) has named fixture directives `qc_artifact` / `fasta_artifact`
  (seeds `params["fasta"]`) / `stale_index_artifact`; **none seeds
  `params["star_index"]`**. Driver `run_heal_scenario` (`heal.py:189-300`) runs the
  **real** loop with only executor/index_builder/poll scripted.
- **Mirrors**: `missing_index` is already in every literal enumeration
  (`FRONT/derive.ts:282`, three dashboard label maps, both e2e pins at length 20) —
  **no literal/count change anywhere**; only the scenario/corpus counts drift.

## Ambiguities / open questions for the interview

1. **Holdout twin?** The brief says "one golden corpus case". House precedent for a
   new *needle* (even on an existing class) is a golden case **plus** an
   independently authored holdout twin, which refreezes `eval-guard`
   (`cram-reference-required`, `reference-mismatch-contig` both did this). The
   runtime-reference-mismatch slice's twin was justified by a *new class*; here the
   class is already covered in holdout (`holdout-missing-index-1`). Decision: golden
   only (eval-guard unmoved) vs golden + twin (eval-guard 14/15 → 15/16).
2. **How the heal scenario seeds the genomeDir.** A corrupt message naming a
   *non*-`genomeParameters.txt` index file (e.g. `<dir>/SA`) contains no `<dir>/…`
   token the current parser extracts, so the scenario must supply `params["star_index"]`.
   Cleanest: a new named fixture directive on `HealScenario` (e.g.
   `star_index_artifact`), mirroring `stale_index_artifact`/`fasta_artifact`
   (additive, defaulted `None`). Alternative: accept that only corrupt
   `genomeParameters.txt` is CI-exercisable (which the *existing* branch already
   catches — so it would not test the new needle). Recommendation: new fixture
   directive.
3. **Exact needle.** AND-guard on `FATAL GENOME INDEX FILE error` **plus** `corrupt`
   (the family rule: phrase + token, so it cannot steal from `missing_index`
   single-file/absence branches, `missing_reference`, or `reference_mismatch`).
   Confirm the phrase against the real STAR wording (`corrupt, or is incompatible`).
4. **Negative controls.** Pin: a genuine STAR missing/version-incompatible line still
   classifies as before; a corrupt line with a `.fai/.bai/…` token is not stolen by the
   single-file branch (single-file tokens are scanned **first**,
   `self_heal.py:143-146`); an unrelated `corrupt` mention (no STAR phrase) stays
   `tool_crash`.
5. **Docstring/count sync**: the heal-guard docstring (`cli.py:4001`, `:4037`) carries
   `23` and `11/23`; `test_heal_scenarios.py:742-818` pins 23 / 11 / 11/23 /
   `len(covered)==17`; `heal_baseline.json` must be refrozen. Confirm all in scope.

## Contradiction surfaced (not papered over)

The brief says "reuse the **unchanged** `_build_star_index`" and reads as a
detector-only slice. That is **half true**: the builder body is unchanged, but the
heal is reachable only via `_is_star_signature`, which the corrupt phrasing does not
match — so a `self_heal.py` change is **required**, and a `HealScenario` fixture hook
is needed to exercise it in CI. The plan must include both, or the scenario will
record an honest `index_unresolvable` give-up instead of the intended recovery.

## Guardrails check (CLAUDE.md)

Layer 2 (detection + self-heal) ✓. No raw-read egress ✓. No correctness over-claim
(the detector names the failure; the patch stays `needs_confirmation`; every give-up
is honest) ✓. No clinical/wet-lab credentials ✓. Not Layer 1 ✓. Not blocker-deferred
(N1 is deferred-but-unblocked, "rarer; same rebuild heal, easy follow-on",
`docs/planning/self-heal-dir-index/prd.md:153`).
