# Card: feat / somatic-swapped-pair

- **Type:** feat
- **Id/slug:** somatic-swapped-pair
- **Owner:** aliz
- **Branch:** feat/somatic-swapped-pair/aliz
- **Source:** inline brief (no GitHub issue) — carried from the `/contig-next`
  recommendation (2026-07-14), the next slice after Strelka2-native VAF shipped v0.34.0.

## Brief

Build the C4 cross-column **swapped-pair smell test** — the deferred sibling slice named in
`docs/planning/somatic-strelka2-vaf/prd.md:175` and
`docs/planning/somatic-vaf-plausibility/vaf-verdict/plan_20260704.md:25`.

In the somatic verdict, derive VAF for **both** the tumor and normal columns of the run's
Mutect2 VCF and emit one WARN-capped plausibility metric that fires when the tumor/normal
VAF relationship is inverted or implausible (somatic calls concentrated in the normal, or a
tumor column that looks germline-clonal at ~0.5/1.0), reusing the shipped
`somatic_plausibility.py` VAF machinery and riding the existing `SOMATIC_PLAUSIBILITY_PACK`
band — no new `FailureClass`, no FAIL severity, no dashboard card.

Honest floor: when the normal column can't be identified from the `##normal_sample=` /
`#CHROM` headers, degrade to **UNVERIFIED, never a false pass** (mirror the existing
header-based tumor-ID fallback); bands stay uncalibrated so it's WARN-only. Test-first with
synthetic two-column VCF fixtures, no real nf-core/sarek run in CI, research-use
corroboration only.

## Why (moat + shipped state)

- **Unblocked, depth-first.** The trigger always exists: every somatic run emits a
  two-column Mutect2 VCF, and the VAF-derivation machinery is already built
  (`verification/somatic_plausibility.py` v0.14.0, `verification/strelka_vaf.py` v0.34.0).
  Natural next slice on the assay that got the last two releases.
- **Catches a catastrophic silent failure incumbents leave to humans.** A tumor/normal swap
  reports the normal's germline as somatic; it passes all current QC. WARN-capped
  corroboration, gets better as models adjudicate ambiguous cases
  (`CAPABILITY_ROADMAP.md:474-476`).
- **Captures eval data, no data/credentials needed.** Synthetic fixtures, no real sarek run
  in CI, no calibration needed for a directional smell. No Layer-1, no clinical claim.

## KNOWN CAVEAT — the VAF-direction signal is the substance (pin FIRST in the dig)

This catches a swap through the **VAF-direction signal** (tumor col ~germline 0.5/1.0, or the
normal col carrying the somatic signal), **not** by trusting labels — which is the point,
since a sheet-level swap is internally label-consistent. Today `somatic_plausibility.py`
reads only the tumor column (via Mutect2's `##tumor_sample=` header); this slice must also
resolve and read the **normal** column.

- Mutect2 emits `##normal_sample=<name>` alongside `##tumor_sample=<name>`; both map to
  `#CHROM` columns. The dig's first task: **confirm the `##normal_sample=` header exists and
  is parseable** on a real sarek 3.5.1 Mutect2 header (the tumor-side resolver is already
  proven — verify the symmetric normal side).
- When the normal column can't be identified → degrade to **UNVERIFIED, never a false pass**
  (same honest floor as the header-based tumor ID). Bands uncalibrated → WARN-only.
- Scope: one metric riding the existing `SOMATIC_PLAUSIBILITY_PACK`, no
  `FailureClass`/dashboard/FAIL-severity.

## Honest contract (mirror the shipped C3/somatic-plausibility contract exactly)

- **WARN-capped, never FAIL, never changes the `contig run`/`verify` exit code** (bands are
  uncalibrated engineering defaults).
- **UNVERIFIED-when-absent, never a false pass:** no Mutect2 VCF with a resolvable
  tumor+normal pair, or no derivable VAF → one honest UNVERIFIED; no VCF at all skips
  silently (structural QC owns a genuinely-missing output).
- Additive to the verdict only — **no new `FailureClass`, model, persisted record,
  dependency, or exit-code/reproduce change**; gated to
  `assay == "somatic_variant_calling"` in `_discover_qc`.
- No raw-read egress (reads a small VCF already on the user's compute); research-use only,
  never a clinical judgement. Test-first with synthetic two-column VCF fixtures — **no real
  nf-core/sarek run in CI**.

## Shipped precedents to mirror

- **Somatic VAF-plausibility slice (v0.14.0)** — `verification/somatic_plausibility.py`,
  `SOMATIC_PLAUSIBILITY_PACK`, `_discover_qc` somatic gate. The tumor-only `median_vaf` this
  slice extends to a tumor-vs-normal comparison. (`CAPABILITY_ROADMAP.md` C4.)
- **Strelka2-native VAF slice (v0.34.0)** — `verification/strelka_vaf.py`, evaluated via
  `evaluate_strelka_vaf_plausibility()` riding the same shared pack. The most recent
  precedent for adding one metric to the shared somatic pack.
- **C1 somatic-concordance slice** — `verification/somatic_concordance.py` locates the
  Mutect2 VCF (by `mutect2` path component). Reuse this discovery seam rather than
  re-globbing.

## Deferred (name in PRD, out of scope for this slice)

- FAIL severity + band calibration on real somatic cohorts.
- PON / germline-resource reference wiring for a real Mutect2 somatic run.
- Any Strelka2 QSS/QSI quality-score plausibility beyond VAF.
- A dashboard card / "corroborated by" surface for the somatic swap signal.
- Any `FailureClass`, self-heal, or eval-corpus/heal-scenario change.
- Any Layer-1 (NL→workflow) surface.
