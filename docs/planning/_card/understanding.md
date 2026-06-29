# Understanding — self-heal-dict-index (Phase 2 dig)

Synthesized from a read-only code-mapping agent (graphify-assisted, every claim
file:line-cited) plus the prior slice's PRD (`self-heal-index-family/prd.md`), which
already **deferred `.dict` for exactly the reason this slice must now solve**. All refs
are in the worktree (identical to `origin/master`, baseline **869 passed, 1 skipped**).

## What the work is really asking

Make the shipped self-heal "missing index → build it → retry" loop recover one more
kind: a **missing GATK sequence dictionary** (`ref.dict`). When a germline (GATK/Picard)
run dies because the FASTA's `.dict` is absent, build it on the user's compute and retry,
recording `built_index_and_retried`; give up honestly (`index_unresolvable` /
`index_build_failed`) when the source FASTA can't be found or the build fails. Never a
false pass.

This is **C2 self-heal breadth**, the highest-leverage moat surface
(`CAPABILITY_ROADMAP.md:114-119`: unattended-completion rate + corpus fuel), on the
**already-shipped** single-file index seam. It serves the **already-shipped germline
assay** (GATK requires a `.dict` next to the reference).

## The seam as it actually ships today (4 kinds, all suffix-strip)

- **Build table** `src/contig/self_heal.py:75-81` — `_INDEX_BUILD: dict[str, Callable[[str],
  list[str]]]`, four rows (`.fai`→`samtools faidx`, `.bai`→`samtools index`,
  `.tbi`→`tabix -p vcf`, `.csi`→`bcftools index`). Value = `lambda src: argv`; the
  table does **not** derive the source.
- **Token extractor** `_parse_missing_index` `self_heal.py:51-72`, regex at `:58`
  `(fai|bai|tbi|csi)` — a **separate hardcoded list**, NOT derived from the table keys.
- **Source derivation** `_index_build_command` `self_heal.py:84-101`, the load-bearing
  line `:97` `source = index_path.removesuffix(ext)` — **pure, no I/O**. True for all
  four kinds because they follow `<data-file>.<index-ext>` (`reference.fasta.fai` →
  `reference.fasta`).
- **Orchestration** `_apply_patch_and_maybe_build` `self_heal.py:390-439`: gated on
  `patch.kind == "reference" and patch.operation.get("build_index")`; parse → command →
  `index_builder(cmd, run_dir)` → outcome string. Outcomes set at `:424`
  (`index_unresolvable`), `:435` (`index_build_failed`), `:439`
  (`built_index_and_retried`). `continue_=False` on the give-ups.
- **IndexBuilder seam** `runner.py:83-126` — `Callable[[list[str], Path], int]` = `(argv,
  cwd) -> rc`; default shells out, tests inject a fake. **No seam change needed.**
- **Patch proposal** `repair.py:56-65` — `missing_index` → `Patch(kind="reference",
  operation={"build_index": True}, …)`. **No change needed** — `.dict` reuses it.
- **Detector** `detect.py:159-176` — line must match `("not found","missing","no such
  file")` AND (`"index" in line` OR ends in `.fai/.bai/.tbi/.csi`) → `missing_index`
  (conf 0.85). `FailureClass.missing_index` at `models.py:204`.

## The two real risks (both must be solved this slice)

### Risk A — `.dict` is the ONE kind that is NOT a suffix-strip (the headline)

The missing file is `ref.dict`; the build **input** is `ref.fasta` / `ref.fa` /
`ref.fa.gz` — a **different base name**, reached by *replacing* the extension, not
stripping a suffix. `"reference.dict".removesuffix(".dict")` → `"reference"` (no
extension) → wrong. So `_index_build_command`'s pure `removesuffix` at `self_heal.py:97`
**cannot** serve `.dict`. The prior PRD anticipated this and recommended generalizing the
table to `{ext: (derive_source_fn, build_argv_fn)}`
(`self-heal-index-family/prd.md:146-149`), but the shipped code never adopted the tuple
(all four kinds are suffix-strip, so it stayed simple). **This slice introduces the
per-kind source-derivation.**

Resolution must probe the filesystem (which of `ref.fasta`/`ref.fa`/`ref.fa.gz`/
`ref.fasta.gz` exists?), which **breaks the "pure, no I/O" contract** of
`_index_build_command`. Design choices for the interview:
- **(Recommended) Generalize the table to `{ext: (deriver, argv_fn)}`** and thread
  `run_dir` (cwd) into the derivation so `.dict` can probe. Suffix-strip kinds keep a
  trivial pure deriver (ignore cwd). `.dict` deriver returns the first existing FASTA
  candidate, else `None` → `index_unresolvable` (honest give-up, never guess).
- Output target = the extracted `index_path` itself (GATK looks for `ref.dict`, i.e.
  replace-extension, NOT `ref.fasta.dict`), so the build is self-consistent:
  `out = index_path`, `input = derived FASTA`.

### Risk B — the detector's first-stage filter may miss GATK's actual wording

`detect.py:165` requires the line to contain one of `("not found", "missing", "no such
file")`. GATK's real missing-dict error reads roughly *"A USER ERROR has occurred: Fasta
dict file …/ref.dict for reference …/ref.fasta **does not exist**. Please … run …
CreateSequenceDictionary"* — **"does not exist"**, which is **not** in that tuple. So
merely adding `.dict` to the second tuple at `:168` is **insufficient**: the line never
reaches the second test. We must either broaden the notfound keyword set (add `"does not
exist"`) or add a `.dict`/sequence-dictionary-aware branch — and choose a corpus
`log_text` whose wording actually trips the rule we ship. **Confirm the exact GATK/Picard
message wording in the interview** (Picard `CreateSequenceDictionary` and the GATK4
wrapper differ). Also keep it conservative so a genuine *wrong-reference* (contig
mismatch) is not mis-classified as a buildable missing dict — that's the deferred
reference-mismatch repair, not this.

## Build-command choice

Prefer **`samtools dict -o <index_path> <fasta>`** — stays in the `samtools` family
already used for `.fai`/`.bai`, minimal new dependency, and produces a GATK-compatible
sequence dictionary. Alternative `gatk`/`picard CreateSequenceDictionary -R <fasta>` is
heavier and writes `ref.dict` implicitly. Confirm `samtools dict` in the interview.

## Exact change-set (from the map)

| Concern | File:line | Change |
|---|---|---|
| Detector wording + token | `detect.py:165` and/or `:168` | handle `.dict` AND "does not exist" (Risk B) |
| Token regex | `self_heal.py:58` | add `dict` to `(fai\|bai\|tbi\|csi)` |
| Build table | `self_heal.py:75-81` | add `.dict`; generalize to `{ext: (deriver, argv_fn)}` |
| **Source derivation** | `self_heal.py:84-101` | **new `.dict` branch** — probe FASTA candidates (Risk A) |
| Corpus seed | `data/detector_corpus.jsonl` | add `missing-index-dict` (`expected_class:"missing_index"`) |
| Tests | `tests/test_detect.py`, `tests/test_self_heal.py` (parse `:1160-1214`, command `:1217-1257`, build-and-retry `:1076-1147`, per-kind parametrize `:1312-1342`) | add `.dict` cases, RED first |
| Patch / IndexBuilder seam / models | `repair.py:56`, `runner.py`, `models.py` | **no change** (reused) |

## Guardrails check (CLAUDE.md)

Layer-2 self-heal ✓ · no raw-read egress (builds a dict from a local FASTA on user
compute) ✓ · no over-claiming (honest `index_unresolvable`/`index_build_failed`; never a
false `built_index_and_retried`) ✓ · test-first, injected builder/executor, no real
`samtools`/GATK in CI ✓ · reuses `missing_index` `FailureClass`, no model change ✓.

## In scope / out of scope

**In:** `.dict` detect + build + retry + honest give-up + one corpus seed, single-file.
**Out (do not drift):** STAR/BWA directory indexes, BAM/CRAM `.csi`, stale-index
detection, the reference/build-*mismatch* repair (wrong reference, not a buildable
missing dict), peak-RSS scaling.
