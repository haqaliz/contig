# Understanding: self-heal-bgzip-reference (Phase 2 deep dig)

## Headline verdict (CONFIRMED with a real reproduction, 2026-07-08)

The live-trigger question — the one make-or-break caveat from the card — is
**settled, and it FLIPPED from the initial guess**:

| Assay / pipeline | Gunzips the fasta before faidx? | Live trigger for the non-BGZF failure? |
|---|---|---|
| **rnaseq** (`nf-core/rnaseq@3.26.0`) | **YES** — `GUNZIP_FASTA` gated on `fasta.endsWith('.gz')` | **NO** — failure erased before faidx |
| **variant_calling** (germline, `nf-core/sarek@3.5.1`) | **NO gunzip module exists in sarek at all** | **YES** |
| **somatic_variant_calling** (`nf-core/sarek@3.5.1`) | **NO gunzip module exists in sarek at all** | **YES** |

So the full **build/redirect self-heal is justified**, scoped to the **sarek
assays** (germline + somatic). rnaseq is correctly excluded — its own
`GUNZIP_FASTA` step makes the failure unreachable there.

This is the opposite of the first dig agent's provisional "(b) detector-only"
verdict, which assumed sarek gunzips "like rnaseq." Reading the **version-exact
pinned source** disproved that: sarek 3.5.1 has no `gunzip` module (only
`spring/decompress`, for FASTQ reads). This is exactly why the card said dig the
trigger first, and why "confirm with a real run" was the right call.

### Evidence (version-exact, not memory)

1. **rnaseq 3.26.0** `subworkflows/local/prepare_genome/main.nf`:
   - L113-114: `if (fasta.endsWith('.gz')) { ch_fasta = GUNZIP_FASTA(...).gunzip... }`
   - L224: `SAMTOOLS_FAIDX(ch_fasta.map {...}, true)` — faidx runs on the GUNZIP
     **output**, never the raw `.gz`. GNU gunzip decompresses plain-gzip AND
     BGZF alike, so faidx never sees a non-BGZF file. No trigger.
2. **sarek 3.5.1**: git tree (`api.github.com/repos/nf-core/sarek/git/trees/3.5.1`)
   contains **no `modules/nf-core/gunzip`**. `subworkflows/local/prepare_genome/main.nf:54`
   passes `fasta` **directly** into `SAMTOOLS_FAIDX(fasta, [ [ id:'no_fai' ], [] ] )`.
   `workflows/sarek/main.nf` + `utils_nfcore_sarek_pipeline` + `samplesheet_to_channel`
   contain no fasta gunzip/decompress (only `SPRING_DECOMPRESS` for spring FASTQ).
   → a plain-gzip'd `--fasta` reaches faidx raw.
3. **Real reproduction** (homebrew samtools/htslib, exact command sarek runs):
   ```
   $ gzip -c ref.fa > ref_plain.fa.gz ; samtools faidx ref_plain.fa.gz
   [E::fai_build_core] File truncated at line 1
   [E::fai_build3_core] Cannot index files compressed with gzip, please use bgzip
   [faidx] Could not build fai index ref_plain.fa.gz.fai      (exit 1)
   ```
   Fix path verified: `bgzip -c ref.fa > ref_bgzf.fa.gz ; samtools faidx ref_bgzf.fa.gz`
   → exit 0, produces `.fai` + `.gzi`. Plain uncompressed `.fa` → exit 0 too.

### Detector token (ground-truth)

Anchor the new detector branch on the **canonical, highly specific** htslib line:
`Cannot index files compressed with gzip, please use bgzip` (secondary anchor:
`fai_build3_core`). Narrow — no benign-log false-match risk, mirroring the
existing STAR / bwa-mem2 two-token gates.

## What the work is really asking

Add a C2 self-heal slice that **recovers** (not just detects) a plain-gzip'd
(non-BGZF) reference FASTA in a Contig-launched **sarek** run: detect the
`faidx` "please use bgzip" failure → re-compress the reference into run-scoped
scratch → redirect `params["fasta"]` → retry → record the recovery. Plus a new
`FailureClass`, a detector-corpus seed + holdout twin, and injected-builder
tests. Reproduce-safe (rerun re-derives from the original path). No real
pipeline run in CI.

### Fix design — recommended direction (decide in PRD/plan)

The provably-correct fix is to **replicate the GUNZIP step that sarek lacks and
rnaseq has**: decompress the plain-gzip'd reference to plain uncompressed `.fa`
in run scratch and redirect. Every downstream sarek tool (faidx, bwa/bwa-mem2
index, GATK dict) accepts uncompressed. Alternative: re-compress to **BGZF**
(faidx-native, smaller scratch) — but must confirm bwa index / GATK dict all
accept bgzip. **Open question for the plan:** uncompressed vs bgzf target.
Leaning **uncompressed** (universal, mirrors the working rnaseq path exactly).

## Affected areas + seams to reuse (from the code-map dig)

- **`src/contig/models.py:208-225`** — `FailureClass` Literal (16 members). Add a
  new member (e.g. `reference_not_bgzf`), or evaluate reusing an existing class.
  Distinct class is cleaner (fix is a recompress, not an index build).
- **`src/contig/detect.py`** — `diagnose_failure` waterfall. New narrow branch
  near the index branches (L200-262 pattern), BEFORE the `tool_crash`
  fallthrough (L320-329, where it lands today at conf 0.4). Capture the FASTA
  path in `evidence` (the Diagnosis carries no path field; it's re-parsed later).
- **`src/contig/repair.py`** — `propose_patches` emits a `kind="reference"`
  patch with a recompress operation.
- **`src/contig/self_heal.py`** — new `_recompress_reference(...)` helper modeled
  on `_build_star_index` (L566-673): run-scoped scratch `<run_id>/healed_index/`,
  the `bgzip`/`gunzip` action via the injectable `IndexBuilder` seam, redirect
  in-memory `params["fasta"]`, `built_paths` one-per-run guard (L834), dispatched
  from `_apply_patch_and_maybe_build` (L698-790). NOTE: this is a whole-file
  redirect like STAR, **not** a `_INDEX_BUILD` suffix-table row (L164-170).
- **Reproduce-safety** — mirror GTF harmonization (`cli.py:472-508,566,659`):
  launch.json stores the **original** `fasta` (already true, `cli.py:566`); never
  persist the scratch path; `rerun` re-enters `_dispatch_run` and re-derives.
- **Corpus** — `src/contig/data/detector_corpus.jsonl` (+ `_holdout.jsonl`): one
  golden `FailureCase` (real `faidx` log_text, `expected_class` = new class).
- **Tests** — mirror the fai/dict injected-builder fail-then-succeed pattern in
  `tests/test_self_heal.py:1566-1610,1737-1755`: (a) recompress success →
  `built_index_and_retried`, `params["fasta"]` redirected, exactly one recompress,
  re-run happened; (b) honest give-up when no fasta in params; (c) one-per-run guard.

## Guardrail check (CLAUDE.md)

- **Layer 2**, dead center: self-heal / recover-more-failures. Not Layer 1.
- **Moat double-hit**: raises unattended-completion (headline Phase-1 metric,
  ROADMAP:101) on the sarek assays + drops a golden corpus case (moat #2).
- No wet-lab/clinical/proprietary-data dependency. No raw-read egress (recompress
  runs on the user's compute). Research-use only.

## Contradiction surfaced (do not paper over)

The card (and the contig-next handoff) framed this around the **reference FASTA**
generically and named **rnaseq**-style pipelines. The dig shows the failure is
**sarek-specific** and **rnaseq-immune**. The slice must gate its heal to the
sarek assays, or it will wire a recovery that the rnaseq path can never exercise
(the same dormant-code trap that BWA/bwa-mem2 fell into).

## Open questions for the PRD

1. Fix target: decompress to plain `.fa` (universal, mirrors rnaseq) vs bgzf
   (faidx-native). Recommend plain uncompressed unless scratch size matters.
2. New `FailureClass` name vs reusing `missing_index` — recommend a new,
   distinct member (`reference_not_bgzf`) for clean corpus labels + repair routing.
3. Detector scope: gate the heal to sarek assays only, or classify the signature
   globally (detector is assay-agnostic) but only wire the redirect where a fasta
   param exists? Recommend: detector classifies globally (corpus value), redirect
   fires wherever `params["fasta"]` is a plain-gzip file (naturally sarek-only,
   since rnaseq's own gunzip means the failure never reaches Contig there).
4. Also handle a BGZF-but-mislabeled or truncated-gzip reference? Out of scope —
   this slice is plain-gzip→(bgzf|plain) only.
