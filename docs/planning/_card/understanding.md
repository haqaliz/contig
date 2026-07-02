# Understanding — feat/rnaseq-concordance (Phase-2 deep dig)

Grounded in two read-only code-mapping agents over this worktree (no `graphify-out/`
graph exists, so both grepped/read directly). Path:line citations inline.

## What the work really asks

Extend the shipped **C1 cross-tool concordance** axis (germline slice, v0.2.0) to a
second assay: **bulk RNA-seq quantification**. Compare the run's own gene-count
matrix against a **second, independent count matrix** supplied by the user, and
emit `kind="concordance"` QC checks that are **WARN-capped** (corroboration, not
ground truth) and **UNVERIFIED when the two share no comparable genes** (never a
false PASS). This is the RNA-seq build named verbatim in
`docs/technical/CAPABILITY_ROADMAP.md:70-71`: "per-gene rank correlation (Spearman)
and the fraction of genes agreeing within a tolerance."

Slice 1 is **user-supplied second matrix** via a new `contig verify
--concordance-counts <matrix>` flag. **Auto-running a second quantifier is
explicitly deferred** to a follow-on (mirrors germline: `--concordance-vcf` in
v0.2.0, `--concordance-auto` in v0.4.0).

## Confirmed facts (both agents)

**The genotype path is NOT reusable — this is a new metric.**
`verification/concordance.py` is entirely VCF/genotype-specific: `parse_vcf`,
`genotype_concordance`, `ConcordanceStats`, and `concordance_results` all operate on
`SiteKey = (CHROM,POS,REF,ALT)` genotypes (`concordance.py:40,87-233`). Its own
comment says "an RNA-seq quantification has no genotypes to agree on"
(`concordance.py:35-36`) and `_CONCORDANCE_ASSAYS = {"variant_calling"}`
(`concordance.py:37`); `evaluate_concordance(a,b,assay="rnaseq")` returns `[]`
today (`concordance.py:247-248`, asserted by
`test_concordance.py::test_evaluate_concordance_skips_non_variant_assay:157`).
→ **Decision: build a parallel `count_concordance.py` module** with its own
stats + `concordance_results`-analog + `evaluate_count_concordance(primary, second,
assay)` gate, rather than overloading the genotype module. Reuse only the shared
seams below.

**Shared seams to mirror (not the genotype logic):**
- `QCResult` fields — `check, status, message, value, expected_range, kind`
  (`models.py:67-75`); `QCStatus = pass|warn|fail|unverified` (`models.py:55`);
  `QCKind` includes `"concordance"` (`models.py:64`). A `_concordance()`-style
  factory hardcodes `kind="concordance"` for dashboard grouping
  (`concordance.py:43-58`).
- **The WARN-cap / UNVERIFIED-never-PASS reduction is free**: `overall_verdict`
  (`models.py:78-96`) already reduces fail>warn>pass and returns `"unverified"` for
  an all-unverified set. As long as our checks only emit `pass|warn|unverified`,
  RNA-seq concordance can never FAIL a verdict — no reduction code to write.
- **UNVERIFIED-on-empty pattern**: germline emits `status="unverified", value=None`
  when nothing is comparable (`concordance.py:201-209`). Mirror for "no shared
  genes".
- **run_qc invocation**: `run_qc.py:79-81` calls `evaluate_concordance(...)` gated
  by `assay`; `assay` param is "used ONLY for gating" (`run_qc.py:60-64`).
- **CLI never-changes-exit contract**: `verify` computes concordance into a
  separate variable and only *attaches/echoes* it — exit codes come solely from
  signature + output-drift (`cli.py:706-763`). New flag must preserve this.
- **CLI primary locator to mirror**: `_resolve_primary_vcf` globs
  `manifest_for("variant_calling").required[0]` under the results dir
  (`cli.py:824-849`), gated by `assay_for_pipeline(record.pipeline)`.

**Where the RNA-seq primary count matrix lives:** the rnaseq structural manifest
declares `required=["*.bam", "*salmon.merged.gene_counts*"]`
(`structural.py:245-249`). ⚠️ The matrix is `required[1]`, **not** `required[0]`
(`*.bam`) — do NOT copy the germline `required[0]` index blindly. Prefer selecting
the count glob **explicitly by pattern** (`*salmon.merged.gene_counts*`) over a
numeric index, so a manifest reorder can't silently point at the BAM.

**No count-matrix parser exists** anywhere in `src/contig/` (confirmed full-repo
grep). We write a new one. Style template: the hand-rolled, stdlib-only,
gzip-aware, streaming VCF parser (`concordance.py:79-110`) and the `csv`-based
samplesheet reader (`samplesheet.py:5,20`).

**No scientific-Python deps** — `pyproject.toml:5-9` ships only pydantic, typer,
cryptography; `uv.lock` has no numpy/scipy/pandas. → **Hand-roll Spearman** (rank
both vectors with average-rank tie handling, then Pearson of the ranks). Consistent
with the repo's stdlib-only ethos; no new dependency. Bonus: Spearman is rank-based,
so it is scale-invariant and robust to raw-count skew — no count normalization
needed.

**Real nf-core filename/columns are UNCONFIRMED from the repo** — the code only ever
references the loose glob `*salmon.merged.gene_counts*`; no fixture pins the exact
layout. Conventionally `salmon.merged.gene_counts.tsv` is `gene_id`, `gene_name`,
then one column per sample. **Our synthetic fixtures define the format the parser
targets** (and the parser should be tolerant: a gene-id column + one-or-more numeric
count columns).

## Test mirror (test-first targets)

- Unit → new `tests/verification/test_count_concordance.py` mirroring
  `test_concordance.py` (identical pair → PASS; divergent → WARN; no shared genes →
  UNVERIFIED; `kind=="concordance"`; gzip parses).
- Integration → extend `tests/verification/test_run_qc.py`
  (`test_run_qc_includes_concordance_when_...`) asserting a divergent RNA-seq pair's
  `verdict != "fail"`.
- E2E → extend `tests/test_cli.py` (`--concordance-counts` emits checks; exit stays
  0 on WARN; JSON includes results; non-rnaseq assay skips cleanly).

## Open questions for the PRD interview (design decisions the code can't resolve)

1. **Per-gene scalar** from a multi-sample matrix: sum counts across samples per
   gene (recommended — deterministic, matches "per-gene" framing) vs mean vs
   require single-sample.
2. **Which checks to emit** (germline emits two): recommend `spearman_concordance`
   (rho) + `fraction_agreeing` (share of shared genes within a relative tolerance),
   optionally a `gene_overlap` analog to `site_overlap`.
3. **Thresholds / tolerance** (all uncalibrated WARN-capped engineering defaults,
   like the RNA-seq *plausibility* slice): Spearman WARN-below (mirror 0.90?),
   per-gene relative tolerance for "agreeing" (e.g. 10%?), fraction-agreeing
   WARN-below (0.90?).
4. **Second-matrix format tolerance**: must it be salmon-shaped, or any TSV with a
   gene-id column + numeric count column(s)? (Recommend the latter, so a
   STAR/featureCounts matrix can corroborate a Salmon one.)
5. **Gene-id join key**: match on `gene_id`; shared-gene set drives everything;
   empty intersection → UNVERIFIED.

## Guardrails check (CLAUDE.md) — clean

Layer-2 verification only (no workflow authoring); deterministic; no raw-read egress
(operates on count matrices on the user's compute); no over-claiming (WARN-cap,
UNVERIFIED-never-PASS); test-first with synthetic fixtures (no real nf-core run in
CI); captures per-assay agreement-distribution eval data (moat #2).
