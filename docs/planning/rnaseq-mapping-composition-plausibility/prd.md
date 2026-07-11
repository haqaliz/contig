# PRD: rnaseq-mapping-composition-plausibility

Status: **draft for review** (review gate pending). Owner: aliz.
Branch: `feat/rnaseq-mapping-composition-plausibility/aliz`.
Capability: **C3 biological-plausibility verification**, RNA-seq slice — the
"exonic-mapping fraction" item named at `docs/technical/CAPABILITY_ROADMAP.md:397` and
deferred by the v0.6.0 rnaseq slice (`docs/planning/rnaseq-plausibility/prd.md:93`).
Sources: `_card/issue.md` (contig-next handoff), `_card/understanding.md` (Phase-2 dig),
two read-only dig agents, and inspection of real runs under `runs/` on disk.

## Problem Statement

Contig's RNA-seq verdict today checks alignment/assignment rates and MultiQC general-stats
plausibility (duplication, rRNA), but it is **blind to where aligned reads fall relative to
gene annotation**. A library with genomic-DNA contamination, failed poly-A selection /
rRNA depletion, or a broken/ mismatched annotation can pass alignment QC while most reads
land **outside exons** — producing a biologically meaningless expression matrix that
"passed." This is exactly the class of silent failure the moat targets: *make every verdict
harder to fool* (`CLAUDE.md`). No incumbent (Galaxy, Terra, Seqera, DNAnexus, Latch,
Basepair) issues a read-composition correctness signal (`FEATURES.md:61-68`).

The signal already exists on disk: nf-core/rnaseq@3.26.0 runs RSeQC `read_distribution`
**by default** and writes `results/star_salmon/rseqc/read_distribution/<sample>.read_distribution.txt`
(confirmed on 4+ real runs in `runs/`). Contig simply doesn't read it — its MultiQC ingest
parses only `report_general_stats_data`, which (verified on a real `multiqc_data.json`) does
**not** carry the exonic/intronic breakdown. So the fix is to parse the RSeQC artifact
directly, exactly as the shipped scrnaseq/methylseq/ampliseq/mag slices parse each tool's
own on-disk QC artifact.

**Who has the problem:** every RNA-seq user (persona A lone computational biologist; persona
B wet-lab scientist who can't code and cannot eyeball an RSeQC table; persona C core facility
shipping results to non-expert PIs). RNA-seq is the single assay exercised end-to-end in CI
(`CLAUDE.md`), so deepening it is depth-first, not breadth.

## Goals & Success Metrics

- **G1 — The RNA-seq verdict gains a read-composition axis.** A completed rnaseq run whose
  RSeQC `read_distribution.txt` is present yields three per-sample QC checks —
  `exonic_fraction`, `intronic_fraction`, `unassigned_fraction` — visible in the verdict/QC
  surface. *Metric:* a gate-level test asserts the three checks appear for `assay="rnaseq"`.
- **G2 — Catches the composition smell, WARN-only.** A synthetic low-exonic /
  high-intronic / high-unassigned fixture drives the corresponding check to WARN with the
  measured value and expected range named; a healthy fixture reads PASS. *Metric:* fixture
  tests at and outside each band.
- **G3 — Honest when absent, never a false pass.** A located-but-unparseable artifact →
  one explicit `rnaseq_composition_qc:<sample>` UNVERIFIED; **no artifact at all → the run is
  unaffected** (no check, no FAIL — structural QC owns genuinely missing outputs). A metric
  that can't be computed (zero denominator, missing row) is omitted, never coerced to 0.
  *Metric:* tests for empty/garbage file → UNVERIFIED; absent artifact → no composition
  checks emitted; zero-denominator → metric omitted.
- **G4 — Additive, no regression.** No new `FailureClass`, model, persisted-record, or
  dependency; no exit-code change; `eval-guard`/`heal-guard` baselines untouched; the
  existing rnaseq alignment + dup/rRNA checks are unchanged. *Metric:* full suite green
  (baseline **1452 passed, 1 skipped**); no real nf-core run in CI.

## User Personas & Scenarios

- **A, lone computational biologist:** gets a WARN that 40% of reads are intronic before
  they spend a day chasing a weird DE result — the tool caught the gDNA contamination.
- **B, wet-lab scientist who can't code:** never opens an RSeQC table; the plain-language
  WARN ("fraction of reads in exons is low") is the only way they'd learn the library was
  off. Sets the approachability bar.
- **C, core facility:** wants a consistent composition guard so a contaminated library
  doesn't silently ship a meaningless matrix to a non-expert PI.

## Requirements

### Must-have (this slice)

- **R1 — RSeQC read_distribution parser.** A new stdlib-only, pure
  `verification/rnaseq_metrics.py::parse_read_distribution(path) -> dict[str, float]` that
  reads the preamble (`Total Reads`, `Total Tags`, `Total Assigned Tags`) and the
  `Group / Total_bases / Tag_count / Tags/Kb` table, and returns up to three metrics
  (below). **Omit-never-guess:** any metric whose inputs are absent/non-numeric or whose
  denominator is 0 is left out of the dict. Gzip-transparent is **not** required (the RSeQC
  output is plain text), but tolerate blank/garbage lines and the `====` rule lines.
- **R2 — Three composition metrics** (all from the `Tag_count` column):
  - `exonic_fraction` = `(CDS_Exons + 5'UTR_Exons + 3'UTR_Exons) / Total Assigned Tags`
  - `intronic_fraction` = `Introns / Total Assigned Tags`
  - `unassigned_fraction` = `(Total Tags − Total Assigned Tags) / Total Tags`
  Denominators are deliberate: exonic/intronic are shares **of tags assigned to features**;
  unassigned is a share **of all tags** (the off-annotation / intergenic-ish smell — the
  nested, overlapping TSS_up_*/TES_down_* windows are **not** summed, which would
  double-count). Values are fractions in `[0,1]`.
- **R3 — `RNASEQ_COMPOSITION_PACK`** in `rule_pack.py`: three WARN-capped rules (no
  `fail_*`), **not** registered in `_RULE_PACKS` (matches the sibling plausibility packs).
  Illustrative uncalibrated defaults (documented as engineering defaults, subject to
  real-data calibration; verified to PASS the healthy yeast test run on disk):
  - `exonic_fraction`  → `warn_below 0.50`
  - `intronic_fraction`→ `warn_above 0.30`
  - `unassigned_fraction` → `warn_above 0.30`
- **R4 — Dedicated `_discover_qc` gate.** A `_locate_rnaseq_composition_qc(run_dir)` helper
  in `runner.py` rglobs `*.read_distribution.txt`, derives a per-sample id (strip the
  `.read_distribution` suffix), and returns `{sample: {slug: value}}` (empty dict for a
  located-but-unparseable file). A new gate block — **additive**, alongside the existing
  `assay == "rnaseq"` plausibility gate (`runner.py:347-349`) — evaluates
  `RNASEQ_COMPOSITION_PACK` when metrics are present, else emits one
  `rnaseq_composition_qc:<sample>` UNVERIFIED (`value=None`, `kind="metric"`). Copy the
  methylseq template verbatim (`runner.py:385-400`).
- **R5 — rnaseq stays OUT of `_DEDICATED_METRIC_ASSAYS`.** The existing `RNASEQ_RULE_PACK`
  alignment/assignment checks still need the generic MultiQC path (`runner.py:245-248`);
  this gate is purely additive and must not divert rnaseq off that path.
- **R6 — Honest contract.** At most WARN, never FAIL, never changes the `contig run`/`verify`
  exit code. UNVERIFIED is never rendered as PASS. Research-use sanity signal, never a
  clinical judgement.
- **R7 — Tests-first (strict TDD).** Unit tests for the parser (inline triple-quoted
  fixtures via a local `_write(tmp_path,…)` helper, the house style) + a committed realistic
  `tests/fixtures/rnaseq/<sample>.read_distribution.txt` (new dir; authored from a real run,
  values may be sanitized) + gate-level assertions in `tests/verification/test_run_qc.py`
  (three checks emitted for rnaseq; not emitted for a non-rnaseq assay; located-but-empty →
  UNVERIFIED; absent artifact → no composition checks). **No real nf-core run in CI.**

### Should-have

- Plain-language `message` on each rule (persona B) — e.g. "fraction of assigned reads
  falling in exons (CDS + UTRs); low suggests gDNA contamination or failed enrichment".

### Nice-to-have (explicitly later, not now)

- A dashboard composition card / mini bar of the three fractions (the CLI/verdict surface
  ships first; UI is a follow-on if not trivial).

## Technical Considerations

- **Chokepoint:** `runner._discover_qc` (`src/contig/runner.py:234`), the single QC
  discovery entry called from `run_pipeline`. One gate block covers CLI and dashboard (the
  dashboard triggers the same run path). No TypeScript change.
- **Reuse:** the shared `evaluate(metrics, rule_pack)` scorer (`rule_pack.py:414`), the
  per-sample UNVERIFIED wrapper pattern from `rnaseq_plausibility.py`, and the locate+gate
  shape from `_locate_methylseq_qc` / the methylseq gate block. The QCResult model is
  unchanged (`models.py:67-75`).
- **Data source:** RSeQC `read_distribution.txt` at
  `results/star_salmon/rseqc/read_distribution/<sample>.read_distribution.txt`, produced by
  default at the pinned nf-core/rnaseq@3.26.0 (`registry.py:15-16`). Confirmed present on
  real runs; **not** in the rnaseq structural manifest (`structural.py:245-249`) and must
  stay out of it (its absence is honest UNVERIFIED/skip, not a structural FAIL).
- **Verification honesty (CLAUDE.md):** WARN-capped uncalibrated bands; UNVERIFIED when
  uncomputable; omit-never-guess on missing inputs. No over-claiming.
- **Reproducibility / egress:** local deterministic parse of a small text file already on
  the user's compute; **no raw-read egress**; no new dependency.
- **Eval data (moat #2):** the three per-sample fractions become a new per-assay
  plausibility distribution captured in the run's QC results, extending the corpus.

## Risks & Open Questions

- **R-risk-1 — Uncalibrated bands cry wolf or stay silent.** Mitigated: lenient defaults
  (verified to PASS the healthy test run), WARN-only, documented as engineering defaults,
  FAIL deferred to real-data calibration — the standing sibling-slice posture.
- **R-risk-2 — Non-default aligner path / filename drift.** The path assumes the
  `star_salmon` RSeQC layout; the rglob on `*.read_distribution.txt` is layout-agnostic
  (matches anywhere under the run). If a future rnaseq config disables `read_distribution`,
  the artifact is absent → honest silent skip, never a false pass.
- **R-risk-3 — Sample-id derivation.** Stripping `.read_distribution` from the filename
  must yield the same sample id the rest of the QC uses; covered by a parser/gate test on a
  realistic filename (`RAP1_UNINDUCED_REP1.read_distribution.txt`).
- **Open:** none blocking — the metric set (3 checks), denominators, and band posture were
  resolved in the interview.

## Out of Scope (confirmed deferred)

- **Gene-body-coverage evenness** — needs the non-default RSeQC `geneBody_coverage` compute
  path (`CAPABILITY_ROADMAP.md:346`); a separate slice.
- **FAIL severity** — until bands are calibrated on real human RNA-seq (only the
  CDS-dominated yeast test profile is available locally).
- **A dashboard composition card** — CLI/verdict surface first.
- **Enabling/forcing RSeQC modules via launch params** — unnecessary; `read_distribution`
  is already default. No launch-seam change.
- **Cross-sample composition aggregation / MAD-outlier** — per-sample checks only this slice.
- Any clinical claim; any Layer-1 workflow authoring.

## Artifact / data contract

Input (read, never written): `<run>/**/<sample>.read_distribution.txt` (RSeQC text).
Output: up to 3 `QCResult`s per sample (`kind="metric"`, `status ∈ {pass,warn,unverified}`)
appended to the run's `qc_results`; plus one `rnaseq_composition_qc:<sample>` UNVERIFIED for
a located-but-unparseable file. No change to `run_record.json` schema, `launch.json`, or the
verify exit code.
