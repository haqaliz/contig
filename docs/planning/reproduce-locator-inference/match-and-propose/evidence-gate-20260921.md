# Evidence gate — C8 locator inference, aspect 2 (match-and-propose)

Date: 2026-09-21 (run pre-merge on `feat/reproduce-locator-matcher/aliz`, at
commit `162fd8c` + the four code commits). PRD decision rule:
`docs/planning/reproduce-locator-inference/prd.md:281-288` — point the sweep and
the matcher at one real published repo, count how many claims genuinely bind, and
only then decide whether the CLI aspect ships as designed, ships narrowed, or
does not ship.

## Subject

- **Repo**: `ritvikK05/rnaseq-reanalysis-htt` (MIT), an independent reanalysis
  of GSE270472 (Kozłowska et al., *Cell & Bioscience* 2025, open access),
  reproducing a published DESeq2 analysis and comparing against the paper's
  Supplementary Table 3. Chosen because it is the canonical real shape: a
  published paper's numbers plus a repo committing **full DESeq2 result
  tables** (`results/tables/`: `02_results_full.csv` ~60k genes × 10 numeric
  columns, shared/missed/extra gene lists, GO tables, sensitivity summary).
  Commit `HEAD` at gate time: shallow clone, latest main.
- **Paper text**: the repo's own README (paper-grade writeup: main-result
  table, sensitivity variants, limitations) — fetchable without paywalls, and
  the claims it states are the analysis's own headline numbers.

## Procedure (real shipped chain, no stubs)

`extract_claims` (deterministic core) or a reviewed draft → draft JSON in the
CLI shape `{id, value, tolerance}` → **unchanged** `load_claims` (real loader) →
**unchanged** `sweep_repo` (real walk of the real repo) → **unchanged**
`match_claims` → independent wrong-bind verification that re-resolves every
bound locator through the real `resolve_pointer`/`_read_table`/`resolve_cell`
and compares at the claim's printed precision. Gate script:
`/var/folders/.../opencode/evidence_gate.py` (throwaway, not committed).

## Results

### Leg A — shipped chain end to end, no human in the loop

- `extract_claims(README.md)` extracted **1 claim**, and it was **wrong**:
  `spearman → 2.0` (the "2" of "log2FC" is the nearest number to the metric
  word; the intended 0.896 was not captured). Extraction on README-style
  prose is known-limited (curated vocabulary tuned for paper prose — a shipped
  C8 honest limit, not a regression).
- `match_claims` **refused it** (`refused_low_information`, 2.0 has 1
  significant digit). M9 behaved exactly as designed on a bad claim.

### Leg B — reviewed draft (the documented extract → review → reproduce flow)

20 claims written from the README's own headline table (1,464; 2,252; 998;
68.2; 81.8; 100.0; 0.896; 256; 2.5e-27; 2,326; 2,226; 68.0; 2,826; 62.6;
0.662; 1.44; 1.34; 244; 72; 108).

- `sweep_repo`: **330,081 candidates, 0 skips** — the sweep's completeness
  holds on a real repo (all nine CSVs enumerated, nothing lost, the
  over-wide-row class absent).
- `match_claims`: **0 bound / 20** — 16 ambiguous (site counts 2 … 218),
  3 refused (100.0 and 68.0 on the M9 deny-list/sig-digit rule, 72 by
  sig-digits), 1 no_candidates (2.5e-27 — no exact candidate; sci-notation
  compares exactly by design).
- Wrong-bind check: **vacuous — no wrong bind found because no bind was
  proposed**. The gate's second question ("is any bind wrong") cannot be
  answered on this repo at the exactly-one rule.

### Why every claim is ambiguous (the finding)

The canonical real repo commits **full result tables**: every plausible value
class appears at scale — the HTT l2fc 1.44/1.34 exist in 143/156 cells
(thousands of genes have an l2fc near any printed value), "recovery" 68.2 has
218 sites, the padj landscape is dense at every order of magnitude. Value
equality alone cannot name a binding site; the disambiguating signal — *which
column* the claim's metric names ("recovery" → the `recovery` column of
`05_sensitivity_summary.csv`) — is present in the repo's **headers** but absent
from the matcher's inputs by design (M2-M4 are value-only).

### R6 observation (fresh-path mismatch)

**Not observed, and read from the scripts, not from a run.** The scripts write
to exactly the committed paths (`scripts/02_deseq2.R` → `results/tables/
02_results_full.csv`, etc. — verified by grep over all six scripts): a fresh
run would rewrite the same paths, so the locator's dependency holds. No R
4.6.1/Bioconductor environment or data download was available, so **no real
run was performed**; the R6-free shape is script-read, not observed. A
timestamped-output-dir repo remains the R6 risk surface, unmeasured here.

## Gate verdict (PRD rule applied)

**The CLI aspect does not ship as designed.** Measured recall of the
value-only, exactly-one matcher on the canonical repo shape is **0/20**; the
proposal channel would be empty on exactly the repos that matter (those with
full published result tables), and the sidecar would degrade to "ambiguous (N
sites)" — i.e. the existing hand-review workflow, unchanged. The PRD's R2
worst case ("real repos are ambiguous everywhere → inference proposes almost
nothing") is now **measured, not assumed**, and the gate has done its job: a
dead end cost two pure modules, not the CLI slice.

**Options, for the founder to choose:**

1. **Ship narrowed — add a column-semantics dimension (recommended).** Keep
   the value matcher, but disambiguate by the claim's own metric vocabulary
   against table **column headers** (and JSON keys): "recovery rate" →
   `recovery` column → 1 site instead of 218. This is principled (the paper
   names the column; the repo's headers are the paper's own semantics, not
   inference from it), is a pure extension of the existing module, and likely
   restores meaningful recall on the canonical shape. It is a **new design
   decision** — M4 changes from value-only to header+value — needing its own
   spec amendment and a second gate run on this same repo.
2. **Declare value-only matching taxonomy-only; do not build the CLI.**
   Record this gate as the evidence; the module stays as the (never-raises)
   substrate for a future semantic matcher.
3. **Ship as designed anyway** (CLI proposes only exactly-one binds): the gate
   predicts an empty proposal channel on full-results repos; only defensible
   if the ICP's repos are "cooperative" (committed headline `results.json`),
   which is exactly the shape slice-1 fixtures assumed — unmeasured
   distribution.

## Honesty scope (in the repo's established voice)

One repo, one gate run, shallow clone at a moving `main`. The paper text was
the repo's own README, not the journal PDF (open-access full text exists but
was not fetched). The reviewed draft is the author-of-record's reading of the
README's headline table — not an independent second reader. Leg A's extraction
failure is a C8 slice-1 known limit, restated here as observed. No real run
performed (R6 read from scripts). Self-graded G1 remains fixture-scoped; the
"is any bind wrong" question is unanswerable at 0 binds. Nothing here touches
the shipped modules — the gate was read-only; the full suite stayed green
(3145 passed / 1 skipped).