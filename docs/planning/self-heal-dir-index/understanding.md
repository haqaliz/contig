# Understanding — self-heal-dir-index (C2 self-heal breadth: STAR/BWA index build)

Phase 2 deep-dig note. Grounded in a full code map + domain research (path:line and
sources cited inline). Three read-only agents ran: seam map, detector/corpus map,
STAR/BWA failure-signature research.

## What the work is really asking

Extend the shipped C2 `IndexBuilder` self-heal seam — which today builds five
**single-file** index kinds (`.fai/.bai/.tbi/.csi/.dict`) and retries — to a missing,
incomplete, or version-incompatible **aligner index** (STAR, BWA), so a run blocked on
one heals autonomously instead of failing. Record `built_index_and_retried`, give up
honestly otherwise, seed golden corpus cases, all test-first with an injected builder
(no real STAR/BWA/nf-core run in CI).

## ✅ The "shape-blocked" contradiction is RESOLVED — not a real blocker

The prior `_card` (self-heal-reference-mismatch, now shipped v0.9.0) listed STAR/BWA
indexes as `shape-blocked`/"agent-confirmed blocked". The dig shows that meant
**implementation-shape complexity, not a feasibility wall.** The seam, detector, and
corpus all extend cleanly; the work is bounded and well-understood. Proceed.

## 🔴 Material correction to the brief's framing: "directory-shaped" fits STAR, NOT BWA

The brief (and the `contig-next` pick) framed this as "directory-shaped STAR/BWA". The
research corrects this — they are **two different shapes**:

- **STAR is directory-shaped.** `STAR --runMode genomeGenerate --genomeDir <dir>` emits
  a *directory* of files: `{Genome, SA, SAindex, genomeParameters.txt}` (core) plus
  `sjdb*`/`*Info.tab` when a GTF was given. The `--genomeDir` is the output dir and must
  be `mkdir`-ed. Completeness ≈ the four core files present + non-empty.
- **BWA is NOT directory-shaped — it is multi-sidecar-file-shaped.** `bwa index ref.fa`
  emits five sidecars *next to the FASTA*: `ref.fa.{amb,ann,bwt,pac,sa}`. This is much
  closer to the existing single-file kinds: the source FASTA is the sidecar path minus
  its suffix (`ref.fa.bwt` → `ref.fa`), so a **`_strip_suffix`-style deriver works for
  BWA** (unlike STAR). (Caveat: `bwa-mem2` emits a *different* sidecar set —
  `.0123/.amb/.ann/.bwt.2bit.64/.pac` — and the two are NOT interchangeable; nf-core/
  sarek defaults to bwa-mem2.)

**Implication:** the slug stays `self-heal-dir-index`, but the design is "directory-OR-
multi-sidecar index build". Likely scope decision: **STAR first** (directory-shaped, the
genuinely new shape, highest RNA-seq/ICP value), **BWA as a sibling/follow-on** (smaller,
reuses the suffix-strip deriver). This is an interview question.

## Affected code (confirmed by the map)

### The self-heal build seam — `src/contig/self_heal.py`
- **Build table** `_INDEX_BUILD: {ext: (derive_source, build_argv)}` (`self_heal.py:119-125`),
  keyed on a leading-dot **file extension**. `.dict` already generalized it to a
  `(SourceDeriver, argv_fn)` tuple (`self_heal.py:128-151`).
- **Derivers:** `_strip_suffix` (`:83-85`, pure, single-file) and `_resolve_dict_source`
  (`:90-112`, filesystem-probing companion-FASTA resolver, `file://`-tolerant). `SourceDeriver`
  signature is `(index_path, ext, run_dir) -> str|None` (`:80`).
- **Parser** `_parse_missing_index` + regex `_INDEX_TOKEN_RE` (`:59,62-73`) — matches ONLY
  tokens ending in `.fai/.bai/.tbi/.csi/.dict`. A STAR/BWA failure names a dir or a
  `genomeParameters.txt`/`.bwt` token, so the parser returns `None` → `index_unresolvable`.
- **Build-once guard** `built_paths: set[str]` (`:563`), keyed on the parsed path string,
  checked at `:488`, added at `:509`; bounds the loop by returning `continue_=False`.
- **Outcomes** in `_apply_patch_and_maybe_build` (`:440-519`): `built_index_and_retried`
  (`:519`), `index_unresolvable` (`:480-486,501-508`), `index_build_failed`
  (guard `:493-499`, build rc≠0 `:511-518`). Trigger gate: patch is `reference` +
  `operation.build_index` (`:476-477`).
- **Builder seam** `IndexBuilder = Callable[[list[str], Path], int]` (`runner.py:83-86`),
  default `default_index_builder` (`runner.py:116-126`) runs argv in `cwd=run_dir`,
  appends to `run.log`, returns exit code. Injected from `cli.py:498` → `self_heal_run`
  (`self_heal.py:532`) → `_apply_patch_and_maybe_build` (`:447,510`).
- **Patch proposal** for `missing_index` is in `repair.py:56-65` (a `needs_confirmation`
  `reference` patch with `operation={"build_index": True}`).

### The detector — `src/contig/detect.py` + `src/contig/models.py`
- `FailureClass` Literal (`models.py:202-219`) has `missing_index`; **no directory/aligner
  sub-type and no contig-mismatch member.**
- `missing_index` is produced by two branches (`detect.py:159-198`): the generic one gates
  on a not-found keyword (`"not found"/"missing"/"no such file"`) co-occurring with the
  literal `index` OR `.fai/.bai/.tbi/.csi`; the `.dict` branch needs a `.dict` token AND an
  absence phrase. **STAR/BWA error strings match NONE of these.** Worse, a STAR/BWA
  "No such file" against the genome FASTA falls through to `missing_reference`
  (`detect.py:200-209`) — a misclassification — else degrades to `tool_crash` (`:258`).
- Wrong-reference/contig-mismatch is kept separate by design (pre-flight
  `reference_check.py`, and the `.dict` branch's deliberate narrowness). The new STAR/BWA
  branches must stay equally narrow so a wrong-reference is not swallowed as a buildable
  index.

### The corpus — `src/contig/data/detector_corpus.jsonl`
- 19 `FailureCase` lines (`models.py:341-349`: `case_id, description, source, events,
  log_text, expected_class`). Existing missing-index cases (`.fai/.bai/.tbi/.csi/.dict`)
  show the exact shape. A new STAR/BWA case = one JSONL line with the real tool error in
  `log_text` and `expected_class:"missing_index"`. `contig eval-detector` (`cli.py:1366`)
  must stay at 100%.
- **No STAR/BWA index signature exists anywhere in src/ or tests/ today** (every `STAR`
  hit is a process name in fixtures, e.g. an OOM case). Net-new detection.

## Verified failure signatures + build commands (domain research)

| Signature fragment (detector) | Tool | Meaning | Heal |
|---|---|---|---|
| `could not open genome file` … `genomeParameters.txt` | STAR | missing/aborted index | rebuild |
| `FATAL GENOME INDEX FILE error:` … `is corrupt, or is incompatible` | STAR | partial/corrupt | rebuild |
| `Genome version:` … `is INCOMPATIBLE with running` STAR version | STAR | **version mismatch (distinct, common w/ iGenomes)** | rebuild **with running STAR version** |
| `[E::bwa_idx_load_from_disk] fail to locate the index files` | BWA | missing sidecars | `bwa index ref.fa` |

- **STAR build:** `STAR --runMode genomeGenerate --genomeDir <dir> --genomeFastaFiles <fa>
  [--sjdbGTFfile <gtf> --sjdbOverhang 100] --runThreadN N --genomeSAindexNbases 14`.
  `--genomeDir/--genomeFastaFiles/--runMode` required; GTF optional-but-recommended for
  RNA-seq; `--genomeSAindexNbases` must be lowered for small genomes.
- **BWA build:** `bwa index ref.fa` → `ref.fa.{amb,ann,bwt,pac,sa}` beside the FASTA.

## 🔴 The key design risk to resolve in the PRD: STAR's deriver needs the run's reference, which the seam does not pass today

Every existing kind derives its source from the **index path itself** (suffix-strip, or a
companion in the same parent dir). **STAR breaks this:** `--genomeDir` is an arbitrary
output directory with *no path relationship* to the source FASTA/GTF. So the STAR deriver
cannot get the FASTA from the genomeDir token — it needs the **run's resolved reference
(FASTA + GTF)**, which today is NOT an input to the `SourceDeriver` seam (`(index_path,
ext, run_dir)` only). Resolving it means threading the launch manifest / resolved
reference params into the deriver (the v0.9.0 chr-prefix harmonization already resolves the
run's GTF — that path is the precedent to reuse). **BWA does not have this problem**
(suffix-strip gives the FASTA). This is the single biggest new piece of plumbing and the
first thing the tech-plan must design.

## Other open questions for the interview (Phase 3)

1. **Scope:** STAR + BWA both this slice, or STAR-first / BWA follow-on? (Two shapes.)
2. **Failure breadth:** just fully-missing, or also **version-incompatible** and
   **corrupt/partial** STAR indexes? All three heal by rebuild and are common with
   iGenomes; including them strengthens the slice but widens detection. (bwa-mem2 vs
   classic-bwa aligner-mismatch — in or out?)
3. **Reproducibility:** a rebuilt STAR index is version-bound — record the STAR version
   (the `genomeParameters.txt` `versionGenome`) in telemetry/provenance so we don't
   re-introduce the version-mismatch class. How/where?
4. **Build-target normalization:** the parsed token may be an inner file
   (`genomeParameters.txt`) while the build target + guard key is the parent **dir** —
   normalize the parser to the directory. For BWA the target is "all five sidecars".
5. **Success check:** `rc==0` + (STAR) genomeDir is a non-empty dir with the core files /
   (BWA) the five sidecars exist. Today there is no `is_dir()`/non-empty check (`:110`,
   `:511` are file/rc-oriented).
6. **`argv_fn` widening:** directory builds need to `mkdir` the genomeDir and may need
   `run_dir`/params; the `(src, idx)` lambda shape may need a third arg.
7. **Corpus:** one golden case per kind (STAR missing, STAR version-incompat?, BWA);
   reuse the `missing_index` `FailureClass` (the detector already classifies it) vs a new
   member — leaning reuse, since rebuild is the heal for all.

## Guardrails check (CLAUDE.md) — clean

- **Layer 2 only** (self-heal/execution). In scope; no Layer-1 drift.
- **No raw-read egress** — index built from a local FASTA/GTF on the user's compute.
- **No correctness over-claiming** — build only when the source FASTA (+GTF) resolves;
  give up honestly (`index_unresolvable`/`index_build_failed`); never a false pass.
- **Test-first** — injected `IndexBuilder`/executor fixtures; no real STAR/BWA in CI.

## Bottom line

Unblocked, bounded, high-leverage. The two things that make it more than a table-row copy
of `.dict`: (a) STAR is directory-shaped and its deriver needs the run's reference params
(new plumbing), and (b) STAR has three distinct rebuild-healable failure modes (missing /
corrupt / version-incompatible) with net-new detector signatures. BWA is the easy sibling.
Recommend taking STAR as the spine of the slice and deciding BWA + the extra STAR failure
modes in the interview.
