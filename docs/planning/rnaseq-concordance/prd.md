# PRD — RNA-seq cross-tool quantification concordance

**Slug:** `rnaseq-concordance` · **Type:** feat · **Owner:** aliz · **Branch:**
`feat/rnaseq-concordance/aliz`
**Capability:** C1 (cross-tool concordance verification), RNA-seq slice — follow-on to
the germline slice shipped v0.2.0.
**Source:** inline brief (`docs/planning/_card/issue.md`) + Phase-2 dig
(`docs/planning/_card/understanding.md`).

---

## Problem Statement

Contig's verified verdict is the moat: no incumbent (Galaxy, Terra, DNAnexus, Seqera,
Latch, Basepair) issues an output-correctness verdict at all
(`FEATURES.md:30-38, 61-68`). Cross-tool **concordance** — running/consuming a
second independent tool on the same data and treating agreement as corroboration — is
a defensible verification primitive shipped today **only for germline variants**
(`CAPABILITY_ROADMAP.md:36-47`). Bulk RNA-seq is one of Contig's three supported
assays but its verdict has **no concordance axis**: a quantification error
(wrong index, annotation drift, aligner-specific bias) that still produces a
structurally-valid, plausible-looking count matrix passes silently. RNA-seq DE is the
highest-volume, highest-non-programmer-pain assay (`ROADMAP.md:49`), so it is the
right place to widen the concordance axis next.

`CAPABILITY_ROADMAP.md:70-71` names the build verbatim: "a second quantifier (for
example Salmon against STAR plus featureCounts, or kallisto), reported as per-gene
rank correlation (Spearman) and the fraction of genes agreeing within a tolerance."

## Goals & Success Metrics

- **G1.** The RNA-seq verdict gains a `kind="concordance"` axis: given the run's own
  gene-count matrix and a user-supplied second matrix, emit a Spearman rank
  correlation and a fraction-agreeing check.
- **G2.** Corroboration only — concordance can move a verdict to at most **WARN**,
  never FAIL, and **never changes the `contig verify` exit code** (mirrors germline).
- **G3.** Honest degradation — when the two matrices share **no comparable genes**,
  report **`unverified`** (never a false PASS).
- **G4.** Capture per-assay agreement-distribution eval data (moat #2): the metric
  values land in the run record like every other QC check.

**Measured by:** the acceptance tests below (a concordant pair → PASS with the metric;
a divergent pair → WARN naming the metric and staying exit-0; no shared genes →
UNVERIFIED). Determinism: identical inputs produce identical metric values, no network.

## User Personas & Scenarios

- **A — lone computational biologist:** ran nf-core/rnaseq (Salmon). Has a
  STAR+featureCounts count matrix from a prior tool. Runs `contig verify <run>
  --concordance-counts featurecounts.tsv` and sees whether the two quantifiers agree
  before trusting the DE input.
- **C — core facility:** wants a second-tool corroboration line on the run report for
  auditability, without re-architecting their pipeline.

## Requirements

### Must-have

- **M1. New count-concordance module** `src/contig/verification/count_concordance.py`
  (parallel to the genotype-specific `concordance.py`, which is not reusable —
  `concordance.py:35-37`). Contains: a matrix parser, the Spearman computation, a
  stats dataclass, a `concordance_results`-analog, and an
  `evaluate_count_concordance(primary, second, assay)` gate.
- **M2. Count-matrix parser** — hand-rolled, stdlib-only, gzip-transparent (mirrors
  the VCF parser style `concordance.py:79-110`). Accepts **any TSV** whose first
  column is a gene id and whose remaining columns are numeric counts; a non-numeric
  second column (e.g. Salmon's `gene_name`) is skipped. **Per-gene scalar = sum of
  counts across all sample columns** → one value per gene id. A row with no numeric
  columns, or an unparseable value, is skipped honestly (never crashes the check).
  - **Header handling:** no explicit header sniff needed — a row whose first column is
    a gene id but whose remaining columns contain **no** parseable numeric value
    (e.g. the `gene_id  gene_name  sample1 …` header, where every retained column is a
    label) is skipped by the same "no numeric columns → skip" rule. The header must
    never become a phantom gene.
  - **Duplicate gene ids:** if a gene id appears on more than one row, **sum** its
    per-gene scalars into the same gene (accumulate, not last-wins). Unit-tested.
- **M3. Spearman rank correlation** — hand-rolled (no scipy/numpy in the repo):
  average-rank tie handling, then Pearson correlation of the ranks, over the
  **shared gene-id set**. Rank-based ⇒ scale-invariant, so no count normalization.
- **M4. Three checks emitted** (all `kind="concordance"`; two WARN-capped, one
  informational):
  - `spearman_concordance`: `value` = round(rho, 4); **WARN if rho < 0.90**, else PASS;
    `expected_range = ">= 0.9"`.
  - `fraction_agreeing`: `value` = fraction of shared genes whose two summed counts are
    within a **10% relative tolerance**; **WARN if < 0.90**, else PASS.
    - **Relative-difference contract (handles zeros/tiny counts):** a gene "agrees"
      when `|a − b| / max(a, b, 1) <= 0.10`. Using `max(a, b, 1)` as the denominator
      means two all-zero genes agree (diff 0), never divides by zero, and damps the
      tiny-count noise case (1 vs 2 → 1/2 = 0.5, correctly "disagrees" but no crash).
      No separate low-count floor in this slice (kept simple; revisit under N4 if
      fixtures show it pathological).
  - `gene_overlap` **(informational, never WARN)**: `value` = fraction of the union of
    gene ids that is shared (`|A∩B| / |A∪B|`), always `status="pass"` — a context
    signal, not a verdict lever. Rationale: a second matrix built on a partial/subset
    annotation legitimately overlaps poorly, so overlap must not cry wolf; the real
    signal lives in `spearman_concordance` + `fraction_agreeing`. (This is the one
    deliberate divergence from germline `site_overlap`, which WARNs below 0.90.)
  - Thresholds (0.90) and tolerance (10%) are **uncalibrated engineering defaults**,
    documented as such (precedent: the RNA-seq *plausibility* slice shipped
    uncalibrated, WARN-capped — `CHANGELOG.md:191-205`). Absorbed by the
    UNVERIFIED-when-no-shared-genes guarantee.
- **M5. UNVERIFIED on too-few shared genes** — the shared gene-id set drives
  everything. When it is empty, **or has fewer than `_MIN_SHARED_GENES = 10`** (a
  Spearman over 1–2 genes is meaningless and could report rho=1.0 → a false PASS), the
  two WARN-capped checks emit `status="unverified", value=None` with a message naming
  that too few genes were comparable to corroborate anything (mirror
  `concordance.py:201-209`). Never PASS. `gene_overlap` still reports its informational
  value (it is meaningful even when the correlation is not). The floor `10` is an
  uncalibrated default, code-overridable, documented as such.
- **M6. Assay gate** — `evaluate_count_concordance` returns `[]` for any assay other
  than `rnaseq`, so callers need not know which assays support it (mirror
  `evaluate_concordance` `concordance.py:236-249`).
- **M7. CLI flag** — `contig verify <run> --concordance-counts <matrix>`:
  - Locate the run's **primary count matrix** by globbing the rnaseq structural
    manifest's count pattern `*salmon.merged.gene_counts*` (select **by pattern**, not
    `required[0]` which is `*.bam` — `structural.py:245-249`), rglob'd under the
    results dir; skip cleanly with a note if none found or the run is not rnaseq
    (`assay_for_pipeline`).
  - Compute concordance into a **separate variable**, attach to the result dict /
    echo it — **never** fold it into `ok`/exit decision (mirror `cli.py:706-763`).
  - Mutually exclusive with the germline `--concordance-vcf` (a run is one assay).
  - `--json` includes the concordance results.

### Should-have

- **S1.** Integration coverage through `run_qc` so a divergent RNA-seq pair yields
  `verdict != "fail"` (the run-level WARN-never-FAIL contract, mirror
  `test_run_qc.py:172-204`).

### Nice-to-have (explicitly deferred, not this slice)

- **N1. Auto-run a second quantifier** (`--concordance-auto`-analog: run Salmon vs
  STAR+featureCounts and self-corroborate) behind an injectable seam like
  `second_caller.py`. Deferred exactly as germline autorun followed one release later
  (v0.4.0). This slice is user-supplied-matrix only.
- **N2. Single-cell concordance** (STARsolo vs alevin-fry) — a separate C1 slice.
- **N3. Dashboard "corroborated by" line** for RNA-seq — the engine already tags
  `kind="concordance"`, so the existing QC panel groups it; no new UI work in scope.
- **N4. Threshold calibration** on real data (promote WARN→FAIL bands).

## Technical Considerations

- **New module, not an extension of `concordance.py`.** The genotype module is
  VCF/SiteKey-specific and its docstring/gate assert RNA-seq is out of scope; a
  parallel `count_concordance.py` keeps both clean. Update the misleading comment at
  `concordance.py:35-36` (or leave the genotype module untouched and let the new
  module carry the RNA-seq gate).
- **Verdict reduction is free.** `overall_verdict` (`models.py:78-96`) already gives
  fail>warn>pass and all-unverified→unverified. Emitting only `pass|warn|unverified`
  means concordance can never FAIL — no reduction code to write.
- **No new dependency.** Spearman + parser are hand-rolled stdlib; keeps the
  zero-scientific-Python-deps posture (`pyproject.toml:5-9`).
- **Reproducibility/verification impact:** adds a deterministic verification axis to
  the run record; no effect on run execution, provenance, or exit semantics beyond the
  new (exit-neutral) checks.
- **Guardrails (CLAUDE.md):** Layer-2 verification only; no raw-read egress (operates
  on count matrices on the user's compute); no over-claiming (WARN-cap,
  UNVERIFIED-never-PASS); test-first with synthetic fixtures (no real nf-core run in
  CI).

## Data Model / Artifact Contract

- No new persisted model. Concordance results are `QCResult`s
  (`check, status, message, value, expected_range, kind="concordance"` —
  `models.py:67-75`) appended to the run's QC results exactly like germline
  concordance. `--json` surfaces them under a `concordance` key (mirror
  `cli.py:724,742`).

## Risks & Open Questions

- **R1 — real salmon filename/columns unconfirmed from the repo.** The code only
  references the loose glob `*salmon.merged.gene_counts*`; no fixture pins the exact
  layout. *Mitigation:* the tolerant "gene-id + numeric columns" parser (M2) does not
  depend on the exact salmon column names; synthetic fixtures define the target
  format. Validate against one real salmon matrix before a release if available.
- **R2 — uncalibrated thresholds** (0.90 / 10%) could WARN on legitimately different
  library preps or annotation versions. *Mitigation:* WARN-capped (never FAIL),
  documented uncalibrated, UNVERIFIED absorbs the no-signal case; calibration is N4.
- **R3 — RESOLVED: zeros / tiny counts in "fraction agreeing".** Handled by the
  `|a−b| / max(a,b,1)` contract (M4): all-zero genes agree, no division by zero, tiny
  counts damped. No low-count floor this slice.
- **R4 — RESOLVED: false PASS from a Spearman over too few genes.** Handled by the
  `_MIN_SHARED_GENES = 10` UNVERIFIED floor (M5).

## Out of Scope

- Auto-running a second quantifier (N1) · single-cell concordance (N2) · new dashboard
  UI (N3) · threshold calibration / FAIL bands (N4) · any change to run execution,
  planning, or Layer-1 workflow authoring · germline/`--concordance-vcf` behavior.

## Acceptance Criteria (test-first)

1. **Concordant pair → PASS.** Two count matrices with near-identical per-gene sums →
   `spearman_concordance` PASS (rho ≈ 1.0, value reported) and `fraction_agreeing`
   PASS, both `kind="concordance"`.
2. **Divergent pair → WARN, exit 0.** Deliberately shuffled/divergent second matrix →
   `spearman_concordance` WARN (rho < 0.90) with the metric in the message;
   `contig verify` exits 0; run-level `verdict != "fail"`.
3. **Too few / no shared genes → UNVERIFIED.** Disjoint gene-id sets, or fewer than
   `_MIN_SHARED_GENES` (10) shared, → `spearman_concordance` and `fraction_agreeing`
   `status="unverified", value=None`; never PASS. `gene_overlap` still reports its
   informational value.
4. **Zero / tiny counts don't crash.** A matrix with zero-count genes parses; all-zero
   genes count as agreeing (`|a−b|/max(a,b,1) = 0`); no division by zero; 1-vs-2
   correctly disagrees.
5. **`gene_overlap` never WARNs.** A pair with low overlap (e.g. subset annotation)
   but high correlation on the shared genes → `gene_overlap` PASS (informational),
   `spearman_concordance` PASS; verdict not dragged.
6. **Duplicate & header rows.** A repeated gene id sums into one gene; the header row
   is not emitted as a phantom gene.
7. **Non-rnaseq assay skips cleanly.** `evaluate_count_concordance(a,b,"variant_calling")
   == []`; `--concordance-counts` on a germline run prints a skip note, changes no exit
   code.
8. **Gzip + tolerant format.** A `.tsv.gz` matrix parses; a second matrix with a
   different column layout (gene-id + numeric only, no gene_name) parses and compares.
9. **Determinism.** Identical inputs → identical metric values; no network.
