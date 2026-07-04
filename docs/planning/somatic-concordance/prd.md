# PRD: somatic-concordance (Strelka2-vs-Mutect2 cross-tool concordance for the somatic verdict)

Status: draft for review. Owner: aliz. Branch: `feat/somatic-concordance/aliz`.
Capability: **C1 concordance axis, somatic assay** (follow-on to germline v0.2.0/v0.4.0,
RNA-seq v0.12.0, and the somatic assay v0.13.0 + VAF plausibility v0.14.0).
Sources: `docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`,
`CAPABILITY_ROADMAP.md:311`, `CHANGELOG.md:44-45`, `FEATURES.md:253`.

## Problem Statement

The somatic (tumor–normal) assay shipped end-to-end (v0.13.0) with a structural verdict,
then gained a biological VAF-plausibility axis (v0.14.0). It still lacks the **independent
cross-tool corroboration** that capability C1 exists to provide: a tool-specific systematic
error in the primary caller can pass every structural check and every plausibility band yet
disagree with a second caller. Every other variant assay that can be corroborated already
has this axis (germline `--concordance-vcf`/`--concordance-auto`); somatic is the gap.

The unlock that makes this the cleanest concordance slice we will ever build: a single
`nf-core/sarek` somatic run **already emits both call sets** — `default_params={"tools":
"strelka,mutect2"}` (`registry.py:30-34`) means a Mutect2 VCF **and** a Strelka2 VCF land in
the same bundle under `variant_calling/<caller>/<tumor>_vs_<normal>/`. Unlike germline
concordance (user supplies a second VCF, or Contig auto-runs bcftools), here **there is no
second tool to run and no user-supplied input** — both VCFs are already on disk.

**Evidence it's real & the moat:** No incumbent (Galaxy, Terra, Seqera, DNAnexus, Latch,
Basepair) issues a cross-tool correctness verdict (`FEATURES.md:61-68`). This is squarely
"make every verdict harder to fool" (`CLAUDE.md`), and it is the explicitly-deferred
follow-on named in three docs (`CAPABILITY_ROADMAP.md:311`, `CHANGELOG.md:44-45`,
`FEATURES.md:253`).

## Goals & Success Metrics

- **G1 — Somatic runs gain a concordance axis, automatically.** When a somatic run's bundle
  contains both a Mutect2 and a Strelka2 VCF, `contig verify` emits a `kind="concordance"`
  **PASS-site-overlap** check corroborating the two callers — **no flag, no user input**.
  *Metric:* an integration test on a synthetic somatic bundle (both callers present) shows
  the concordance result appears in the verdict's QC results.
- **G2 — At most WARN, never changes the exit code.** Concordance corroborates; it never
  promotes UNVERIFIED to PASS and never drives the verify exit code. *Metric:* a test proves
  a divergent pair emits WARN and the exit code is unchanged from the no-concordance run.
- **G3 — Honest UNVERIFIED, never a false pass.** Below a minimum shared-PASS-site floor
  (too few comparable sites to corroborate), the check is `unverified` with no severity.
  *Metric:* a test with < N shared PASS sites yields `unverified`, not `pass`.
- **G4 — Silent, correct skips.** A run missing either caller's VCF (or a non-somatic assay)
  emits **no** somatic concordance result and no error. *Metric:* tests for mutect2-only,
  strelka-only, and non-somatic runs all skip cleanly (structural QC already covers a
  genuinely missing output).
- **G5 — No regression, no network, no tool execution.** The full suite stays green; the
  check is pure local VCF parsing over synthetic fixtures (no real nf-core/sarek run in CI).

## User Personas & Scenarios

- **A, lone computational biologist:** runs a somatic tumor–normal analysis; wants a
  one-glance signal that two independent callers agree on the confident calls, without
  scripting a second caller or reformatting VCFs.
- **C, core facility:** ships somatic results to non-expert PIs; wants a consistent
  cross-tool corroboration line on every somatic verdict so a caller-specific artifact is
  caught before it reaches the PI.

## Requirements

### Must-have (this slice)

- **R1 — New somatic concordance module** `src/contig/verification/somatic_concordance.py`.
  A pure function of two VCF paths. Mirrors `concordance.py`/`count_concordance.py`:
  `kind="concordance"` QCResults, WARN-cap thresholds, a min-shared-sites floor →
  UNVERIFIED, gzip-transparent open. It does **not** reuse germline `parse_vcf`
  (first-sample-GT-only, load-bearing for germline).
- **R2 — PASS-site-overlap metric (the one metric this slice emits).** Parse each caller's
  VCF into the set of **PASS** site keys `(CHROM, POS, REF, ALT)`, where PASS means
  `FILTER ∈ {"PASS", "."}` (net-new FILTER-aware parsing; germline concordance ignores
  FILTER). Emit `somatic_site_overlap = |A∩B| / |A∪B|` (Jaccard over PASS sites), PASS
  at/above the WARN threshold, WARN below it. The message names both callers and the shared
  vs union counts, by basename, for auditability. Sample-agnostic by construction — it never
  reads GT or a tumor column, sidestepping the Strelka-no-GT problem.
- **R3 — UNVERIFIED floor.** When the number of shared PASS sites (or the union) is below a
  documented minimum (mirror `_MIN_SHARED_GENES=10` shape from `count_concordance.py:41-43`),
  emit `unverified` (no severity), never a `pass`.
- **R4 — Auto-wire into the somatic verdict** at the `runner.py:_discover_qc` somatic branch
  (`runner.py:78-107`). Locate the Mutect2 VCF exactly as the plausibility slice already does
  (`"mutect2"` as a **path component** below the run dir, `runner.py:82-93`) and add the
  **symmetric Strelka selector** (`"strelka"` path component). **Union** Strelka's split
  outputs (`*.somatic_snvs.vcf.gz` + `*.somatic_indels.vcf.gz`) into one call set. Call the
  new evaluator with (mutect2, strelka) and append its results to the somatic QC list.
- **R5 — Honest edges.** Missing/unreadable either VCF → no result (skip). Non-somatic assay
  → the module/branch is never reached. Neither path crashes, neither emits a false pass.
- **R6 — At-most-WARN, exit-code-neutral.** The emitted checks are WARN-capped and carry
  `kind="concordance"`; they must not change the somatic verdict's exit code (concordance
  never enters the fail-reduction beyond WARN).
- **R7 — Tests-first, synthetic VCF fixtures via `tmp_path`.** Mirror `test_concordance.py`
  + `test_somatic_plausibility.py`. Cover: concordant pair (PASS overlap high → pass),
  divergent pair (low → warn), below-floor (→ unverified), FILTER filtering (a non-PASS
  record excluded from the sets), Strelka split-file union, gzipped inputs, mutect2-only /
  strelka-only / non-somatic (→ skip), and the gate-level "appears in verdict, never changes
  exit" behavior.

### Should-have

- The result message states the FILTER policy (PASS-only) and the two caller basenames so a
  reader understands what was compared.

### Nice-to-have (explicitly later, not now)

- **Tumor-VAF agreement** at shared sites (Strelka2 AF is tier-count-derived; cross-caller
  VAF alignment is a real complexity — deferred).
- An explicit `contig verify --concordance-somatic` echo via `_echo_concordance`
  (auto-in-verdict covers the value; a printed CLI surface is additive).
- FAIL severity once the overlap band is calibrated on real tumor–normal data.
- Per-caller **PASS-call-count** context as a second informational check.

## Technical Considerations

- **Chokepoint:** `src/contig/runner.py:_discover_qc` (`runner.py:39`, somatic branch
  `runner.py:78-107`). One insertion covers CLI and dashboard (both verify through the same
  path). No CLI flag, no TypeScript change.
- **Module boundary:** new `somatic_concordance.py` keeps `concordance.py` germline-focused.
  Reuse only the *shape* (QCResult builder, thresholds, gzip idiom, min-shared floor), not
  the GT parser.
- **FILTER-aware parse is net-new:** germline `parse_vcf` (`concordance.py:87-110`) ignores
  the FILTER column (col 6). The somatic parser keeps a record only when `FILTER ∈ {"PASS",
  "."}` and stores the site key; it reads no sample columns at all.
- **Strelka split output:** Strelka somatic writes `*.somatic_snvs.vcf.gz` and
  `*.somatic_indels.vcf.gz` (`tests/test_somatic_end_to_end.py:36-40`); the Strelka call set
  is the **union** of both files' PASS sites.
- **Verification honesty (CLAUDE.md):** corroboration only — at most WARN; UNVERIFIED below
  the floor; never a fabricated agreement. Research-use, never a cancer diagnosis.
- **Reproducibility / egress:** deterministic; operates only on VCFs already in the run dir
  on the user's compute; no raw-read egress, no network, no tool execution.
- **Eval data captured:** somatic caller-agreement (overlap) per run extends the reference
  distribution and flags divergent somatic runs into the corpus (`CAPABILITY_ROADMAP.md:100-101`).

## Data Model / Artifact Contracts

- **No model change.** Reuse `QCResult(kind="concordance")` (`models.py:67-75`);
  `"concordance"` is already in `QCKind` (`models.py:64`) and grouped by the dashboard's QC
  panel. Thresholds are documented engineering defaults, not clinical claims.

## Risks & Open Questions

- **R-risk-1 — Uncalibrated overlap band.** The WARN-below threshold is a best-effort default
  (like every concordance/plausibility slice so far). Mitigated: WARN-capped only, no FAIL;
  calibration + FAIL severity explicitly deferred.
- **R-risk-2 — Representation differences inflate disagreement.** Mutect2 and Strelka2 can
  represent the same variant with different normalization / left-alignment, lowering literal
  `(CHROM,POS,REF,ALT)` overlap. Mitigated: this is the documented, honest limitation of
  site-key concordance (`concordance.py:14-17`); PASS-only filtering reduces the noise floor;
  normalization is out of scope for slice 1 and disclosed. Overlap is corroboration, not F1
  against truth, so a modest representation gap reads as a (truthful) lower overlap, never a
  false pass.
- **R-risk-3 — Strelka `##tumor_sample=` absent.** Not a risk here — the metric is
  sample-agnostic and reads no sample column, so Strelka's fixed NORMAL/TUMOR naming and
  missing tumor-sample header do not matter.
- **Open:** the exact min-shared-sites floor and the WARN threshold values — a tech-plan
  detail; both are WARN-capped and absorbed by the UNVERIFIED-below-floor guarantee.

## Out of Scope (confirmed deferred)

- Tumor-VAF agreement / any genotype-concordance metric for somatic.
- Variant normalization / left-alignment before comparison.
- FAIL-severity somatic concordance (until calibrated on real data).
- An explicit `contig verify` flag / CLI echo (auto-in-verdict is the surface for slice 1).
- Detector corpus / new `FailureClass` (concordance is a verdict axis, not a run failure).
- Any clinical claim; any Layer-1 workflow authoring.
