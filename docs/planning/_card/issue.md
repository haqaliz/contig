# Card: feat / somatic-strelka2-vaf

- **Type:** feat
- **Id/slug:** somatic-strelka2-vaf
- **Owner:** aliz
- **Branch:** feat/somatic-strelka2-vaf/aliz
- **Source:** inline brief (no GitHub issue) — carried from the `/contig-next`
  recommendation (2026-07-14, re-run after `self-heal-cram-bam` was found blocked).

## Brief

Add a **Strelka2-native VAF plausibility** metric to the somatic verdict (capability
**C4**, biological-plausibility axis of the somatic assay). This closes the named
"non-Mutect2 VCFs degrade to UNVERIFIED" gap the shipped Mutect2-only VAF slice left open
(`CAPABILITY_ROADMAP.md` C4: "Strelka2-native VAF (tier-count derivation — non-Mutect2
VCFs degrade to UNVERIFIED)").

Today `verification/somatic_plausibility.py` computes `median_vaf` **only** from the
**Mutect2** VCF (FORMAT `AF`, else `AD_alt/DP`; tumor identified by `##tumor_sample=`).
Every Contig somatic run launches sarek with `--tools strelka,mutect2`, so a **Strelka2**
call set is always on disk too — and the shipped C1 somatic-concordance slice already
**locates and parses both call sets**. This slice adds a Strelka2-specific VAF derivation
so the somatic VAF axis fires from the Strelka2 call set as well (corroboration /
verdict-hardening), instead of degrading to UNVERIFIED on a non-Mutect2 VCF.

## Why (moat framing)

- **Verdict-hardening** (moat rule #2): turns a UNVERIFIED gap into a real check —
  "widen what we can verify" — on an assay `CLAUDE.md` says is "being hardened to the
  [RNA-seq] bar."
- **Fully unblocked:** the Strelka2 VCF is already produced and already located by the
  C1 somatic-concordance seam; this is a parser + metric, no new pipeline wiring, no new
  dependency.
- **Corpus fuel** (moat #2): a second-caller VAF distribution joins the eval corpus.
- **Depth-first** on the shipped somatic assay; reuses the shipped dedicated-parser
  pattern (`somatic_plausibility.py`, plus the ampliseq/mag/methylseq per-tool parsers).

## KNOWN CAVEAT — Strelka2 VAF derivation (pin this FIRST in the dig)

Strelka2 is the reason this was deferred from the Mutect2-only slice: **Strelka2 somatic
VCFs carry no conventional per-sample `GT` and no `AF`** (the C1 somatic slice notes its
metric was "sample-agnostic" because "Strelka2 somatic SNVs carry no conventional
per-sample `GT`"). VAF must be **derived from Strelka2's tier-count FORMAT fields**:

- **SNVs** (`*.somatic_snvs.vcf.gz`): per-allele tier counts `AU`, `CU`, `GU`, `TU` (each
  a `(tier1, tier2)` pair). VAF ≈ tier1 ALT count / (tier1 REF count + tier1 ALT count),
  reading REF/ALT bases to pick the right `?U` field.
- **Indels** (`*.somatic_indels.vcf.gz`): `TAR` (tier1,tier2 REF) and `TIR` (tier1,tier2
  ALT). VAF ≈ TIR.tier1 / (TAR.tier1 + TIR.tier1).
- **Tumor column** identified by Strelka2's **`NORMAL`/`TUMOR` sample-column convention**
  (fixed column names), NOT Mutect2's `##tumor_sample=` header.

The dig's first task: confirm this formula + column resolution against a **real Strelka2
somatic header** (the C1 somatic-concordance slice already reads these files — reuse/verify
its assumptions). The honest fallback (UNVERIFIED when tier fields are absent/unparseable)
absorbs any edge case.

## Honest contract (mirror the shipped C3/somatic-plausibility contract exactly)

- **WARN-capped, never FAIL, never changes the `contig run`/`verify` exit code** (bands are
  uncalibrated engineering defaults; reuse `SOMATIC_PLAUSIBILITY_PACK`'s band shape).
- **UNVERIFIED-when-absent, never a false pass:** no Strelka2 VCF, no derivable tier VAF,
  or an unidentifiable tumor column → one honest UNVERIFIED; no VCF at all skips silently.
- Additive to the verdict only — **no new `FailureClass`, model, persisted record,
  dependency, or exit-code/reproduce change**; gated to `assay == "somatic_variant_calling"`
  in `_discover_qc`.
- No raw-read egress (reads a small VCF already on the user's compute); research-use only,
  never a clinical judgement. Test-first with synthetic Strelka2 VCF fixtures — **no real
  nf-core/sarek run in CI**.

## Shipped precedents to mirror

- **Somatic VAF-plausibility slice (Unreleased)** — `verification/somatic_plausibility.py`,
  `SOMATIC_PLAUSIBILITY_PACK`, `_discover_qc` somatic gate. The Mutect2 half this slice
  extends. (`CAPABILITY_ROADMAP.md` C4.)
- **C1 somatic-concordance slice (Unreleased)** — `verification/somatic_concordance.py`
  already locates the Mutect2 VCF (by `mutect2` path component) and the Strelka2 split
  `*.somatic_snvs`/`*.somatic_indels` files (by `strelka` component). **Reuse this
  discovery seam** rather than re-globbing.
- Dedicated per-tool parsers (`ampliseq_metrics.py`, `mag_metrics.py`,
  `methylseq_metrics.py`, `scrnaseq_metrics.py`) — the stdlib-only, omit-never-guess parser
  shape.

## Deferred (name in PRD, out of scope for this slice)

- FAIL severity + band calibration on real somatic cohorts.
- The cross-column swapped-pair smell test (a sibling deferred item — separate slice).
- PON / germline-resource reference wiring for a real Mutect2 somatic run.
- Any Strelka2 QSS/QSI quality-score plausibility beyond VAF.
