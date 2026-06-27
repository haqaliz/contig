# Understanding: self-heal-index-family

Phase-2 dig note (grounded in a code map of this worktree). File:line refs are to
`src/contig/` unless noted. This slice **extends** the just-shipped `.fai` missing-index
self-heal to the rest of the single-file index family.

## What the work is really asking

The `.fai` slice already built the whole machine: the injectable `IndexBuilder` seam,
the gated apply-and-build helper, the honest outcome vocabulary, and the corpus seed.
This slice only has to **generalize the three `.fai`-specific spots** so the same loop
recovers `.bai`, `.tbi`/`.csi`, and (caveat below) `.dict`.

## What already exists (do NOT rebuild)

- **Seam.** `IndexBuilder = Callable[[list[str], Path], int]` (`runner.py:77`),
  `default_index_builder` shells out and tees to run.log (`runner.py:107-117`).
- **Gated apply-and-build helper.** `_apply_patch_and_maybe_build`
  (`self_heal.py:367-414`) parses the path, calls the builder, and branches the
  outcome. Already factored into a single helper invoked at every gated-apply site
  (the M4a requirement of the prior slice).
- **Outcome vocabulary.** `index_unresolvable` / `index_build_failed` /
  `built_index_and_retried` recorded at `self_heal.py:401/410/414`; `RepairStep.outcome`
  is a free `str` (`models.py:225`), so new outcomes need no model change.
- **Repair proposal is already index-agnostic.** `repair.py:56-65` proposes
  `Patch(kind="reference", operation={"build_index": True}, risk="needs_confirmation")`
  — no extension hard-wired.
- **Detector keys on `.fai .bai .tbi .csi`** (`detect.py:168`), confidence 0.85.
- **Corpus.** One golden `missing_index` case in
  `src/contig/data/detector_corpus.jsonl` (the `.fai`/`fai_load` line).
- **Test pattern.** `tests/test_self_heal.py:1047-1147` — `_fai_executor` (fail-then-
  succeed) + `_building_builder` (records argv, creates the index file, returns rc);
  four tests cover build-and-retry, exact argv, failed-build, and unparseable-path.

## The actual gap (the three `.fai`-specific spots to generalize)

1. **Token regex** `_FAI_TOKEN_RE = re.compile(r"\S+\.fai(?=\s|$|[:,;])")`
   (`self_heal.py:55`) — only matches `.fai`.
2. **Parse** `_parse_missing_fai(diagnosis)` (`self_heal.py:58-68`) — returns a `.fai`
   path only; must return the path *and which extension* so the build can dispatch.
3. **Command** `_fai_build_command(fai_path)` (`self_heal.py:71-78`) — hardcodes
   `["samtools","faidx", strip(".fai")]`; must become an extension→command table.

`_apply_patch_and_maybe_build` (`:396`, `:405`) calls these two functions; the variable
`fai` and the `.fai`-specific detail strings (`:411`) generalize with them.

## The path→command table (the design decision for the interview)

| Ext | Source derivation | Build command | Wrinkle |
|---|---|---|---|
| `.fai` | strip `.fai` → FASTA | `samtools faidx <fasta>` | (shipped) |
| `.bai` | strip `.bai` → `<x.bam>` | `samtools index <x.bam>` | assumes `x.bam.bai` form; bare `x.bai` (GATK) is rarer |
| `.tbi` | strip `.tbi` → `<x.vcf.gz>` | `tabix -p vcf <x.vcf.gz>` | needs a preset; `-p vcf` is the dominant case |
| `.csi` | strip `.csi` → `<x.vcf.gz>` | `bcftools index <x.vcf.gz>` | **ambiguous**: `.csi` is also a coord-sorted BAM index (`samtools index -c`) |
| `.dict` | NOT a suffix strip (`ref.fasta`→`ref.dict`) | `samtools dict <ref.fasta> -o <ref.dict>` | **detector change required** + source-FASTA resolution is non-trivial |

## Caveats / decisions to settle (Phase 3)

- **C1 — `.dict` is materially harder.** It is (a) absent from the detector keyword list
  (`detect.py:168`), so detection must be extended this slice if `.dict` is in scope —
  the prior slice deliberately kept detection unchanged; and (b) its source FASTA is not
  a suffix strip (`ref.dict` ↔ `ref.fasta`/`ref.fa`, ambiguous). **Recommendation:**
  ship `.bai`/`.tbi`/`.csi` (zero detector change, clean suffix derivation) and treat
  `.dict` as either a stretch goal in this slice or an explicit further follow-on.
- **C2 — `.csi` command choice.** Lean VCF (`bcftools index`) since `.tbi/.csi` are
  overwhelmingly VCF/tabix in nf-core flows; note the BAM-`.csi` case as out of scope.
- **C3 — STAR/BWA directory indexes** stay deferred (multi-file/dir shape, not a single
  parsed path). Single-file indexes only.
- **C4 — Stale-index detection** stays out of scope; detector catches fully-missing only.
- **C5 — Corpus.** Seed one golden case per new kind (per the brief) into
  `detector_corpus.jsonl`; keep the detector eval green.
- **C6 — Surface footprint.** Match the `.fai` slice: `repair_history` +
  `repair_progress.jsonl` only; no dashboard/report rendering this slice.

## Guardrails check (CLAUDE.md)

Layer 2 (run + self-heal) only; no Layer-1 authoring. No raw-read egress — builds run on
the user's compute through the injected seam. Bounded by the existing `max_attempts`
(one build per missing-index path). Test-first via the injected builder/executor fakes;
no real samtools/tabix/bcftools/Nextflow in CI. Gets better as base models improve (a
smarter diagnoser flows through the same bounded build-and-retry). No contradictions
found between the brief and the code; the one nuance is `.dict` (C1).
