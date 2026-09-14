# PRD: reference-known-sites-capture

| | |
|---|---|
| Slug | `reference-known-sites-capture` |
| Branch | `feat/reference-known-sites-capture/aliz` |
| Status | Draft for review |
| Sources | `docs/planning/_card/issue.md` (inline brief), `docs/planning/_card/understanding.md` (Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md` C5, nf-core/sarek 3.5.1 `nextflow_schema.json` + source (pinned revision) |
| Capability | **C5 slice 2** (follow-on to the reference-identity capture slice) |

## Problem Statement

Contig's C5 reference-integrity capability pins the reference a run used — FASTA/GTF
identity + checksums captured into `ReferenceIdentity` at finalize, rendered in
`contig methods` + the HTML provenance panel, round-tripped through `rerun`/`resume`
(`docs/technical/CAPABILITY_ROADMAP.md:1183-1200`). The **known-sites** a variant-calling
run used — the dbSNP/known-indels/known-snps resources consumed by BQSR, HaplotypeCaller,
and VQSR — are the second data class the run ran against, and they are **not captured
anywhere**. A reproduction claim "runs against reference X" is incomplete without them:
the same FASTA with a different dbSNP build or a missing known-sites resource produces a
different, non-reproducible result. This is squarely the reproduce moat (`CLAUDE.md` #2).

The C5 deferral listed known-sites as "not visible to Contig today: nf-core config
assets, not CLI params — needs a `--known-sites` design" (`CAPABILITY_ROADMAP.md:1197-1198`).
**The Phase-2 dig falsified that premise for sarek 3.5.1, Contig's pinned revision**
(`src/contig/registry.py:27,47`): sarek exposes `dbsnp`, `dbsnp_tbi`, `dbsnp_vqsr`,
`known_indels(+tbi/vqsr)`, `known_snps(+tbi/vqsr)` as first-class CLI schema params in
group `reference_genome_options`, all `default: None`; the config-asset half is real only
in iGenomes mode (`conf/igenomes.config` `GATK.GRCh38` block, `s3://ngi-igenomes/...`
paths). So the design is a genuine **CLI/passthrough** design, not a "read config assets"
design. This PRD is built on the verified surface.

**Evidence it matters:** sarek consumes these in BQSR (`main.nf:186-191,512-520` —
`known_sites_indels = dbsnp.concat(known_indels)`), germline HaplotypeCaller (`--dbsnp` on
the GATK command, `gatk4/haplotypecaller/main.nf:30`), and VQSR labels — the exact
resources whose version/presence changes call results. No incumbent (Galaxy, Terra, Seqera,
etc.) records which known-sites a run used (`FEATURES.md:61-68`).

## Goals & Success Metrics

- **G1 — Capture the three germline known-sites roles.** A `contig run --dbsnp P
  --known-indels P2 --known-snps P3` run records all three (path + sha256) in
  `ReferenceIdentity`. *Metric:* `tests/test_bundle.py`-style fixtures — explicit paths →
  sha256s recorded; a missing/unreadable file → checksum `None`, never a fabricated hash;
  no flags → known-sites absent.
- **G2 — Honest iGenomes handling.** A `--genome GATK.GRCh38` run records which known-sites
  sarek will resolve (role + iGenomes asset path), checksum `None` (pipeline-downloaded) —
  mirroring the existing `mode="igenomes"` handling. *Metric:* key-only capture, `None`
  checksums, no attempt to hash s3:// paths.
- **G3 — Zero false capture.** A non-variant assay or a run with no known-sites flags
  records nothing; known-sites never change the verdict or exit code. *Metric:* verdict/
  exit-code tests unchanged for the fixture suite.
- **G4 — Rendered and round-tripped.** Known-sites appear in `contig methods` + the HTML
  provenance panel, and survive `rerun`/`resume`. *Metric:* `tests/test_methods.py` /
  `tests/test_report.py` render assertions + a manifest round-trip test.

## User Personas & Scenarios

- **A, lone computational biologist:** re-runs a variant-calling analysis months later (or
  another lab runs it). The methods paragraph must name the dbSNP build and known-indels
  resource the run used, not just the FASTA. Today the paragraph can't; after this slice it
  can, with hashes.
- **D, biotech researcher:** needs provenance that proves which resource set a result came
  from — a versioned dbSNP is a reproducibility pin, like a pinned tool version.
- **Founder / evaluator:** this is the second data-pinning slice of the least-complete
  capability; it compounds moat #2 by making the reproduce guarantee describe the *data*
  the run consumed, not only the pipeline and the FASTA.

## Requirements

### Must-have

- **R1 — CLI flags on `contig run`.** `--dbsnp PATH`, `--known-indels PATH`,
  `--known-snps PATH` (each single, optional; the `--fasta/--gtf` shape, `cli.py:405-408`),
  valid only for the variant assays (`variant_calling`; somatic known-sites such as `pon`/
  `germline_resource` are explicitly deferred). Merged into `params` beside
  `resolve_reference` (`cli.py:657`) so `build_nextflow_command` forwards them
  (`runner.py:1326-1327`). A flag on a non-variant assay is refused, not silently ignored.
- **R2 — Capture into `ReferenceIdentity`.** Extend the model (`models.py:207-218`) with a
  known-sites structure (see Data Model), populated by an extended
  `compute_reference_identity` (`bundle.py:147-180`) at `_finalize` (`self_heal.py:1715`)
  from `record.parameters`. The iGenomes early-return (`bundle.py:163-164`) must not
  swallow the known-sites branch.
- **R3 — Honest degradation everywhere.** Missing/unreadable/absent known-sites file →
  checksum `None` (never fabricated, never a run failure); no flags → known-sites absent;
  iGenomes → role + asset path with checksum `None`. Reuse the `_hash` guard discipline
  (`bundle.py:168-172`). Hash the data VCF.gz only, skip `.tbi` (the FASTA/GTF precedent).
- **R3b — Pre-flight existence warning.** Because a known-sites file has no Contig-side
  consumer today, a typo'd `--dbsnp` path would otherwise sail through and hard-fail hours
  later in sarek BQSR, then memorialize a `None`-checksum "pinned" resource as the
  reproduce record. Each explicit path is existence-checked at pre-flight and a **warning**
  (not a refusal — honest-degradation is preserved) names the missing file before the run
  launches. Mirrors the FASTA/GTF pre-flight posture without the consistency refusal.
- **R4 — Manifest round-trip.** Known-sites land on `LaunchManifest` (`cli.py:769-791`)
  and are re-fed by both `rerun` (`cli.py:837-902`) and `resume` (`cli.py:2509-2572`),
  exactly like `genome/fasta/gtf`.
- **R5 — Render.** Known-sites appear in `contig methods` (`_reference_clause`,
  `methods.py:56-79`) and the HTML provenance panel (`report.py:409-428`), with the
  iGenomes "pipeline-downloaded" phrasing. **Build naming is scoped, not promised:** the
  paragraph names the file (basename, per the `_reference_clause` pattern) and its hash;
  it names the *build* only when the filename or the iGenomes asset map carries it. Never
  resolved, never fabricated (the `annotation_version` discipline, `models.py:216`).

### Should-have

- **S1 — `contig show` / dashboard-neutral visibility.** The HTML report carries the full
  table; the CLI text report carries a compact clause. Dashboard TS rendering is **out of
  scope** (the dashboard carries no `reference_identity` TS type today — a separate slice).

### Nice-to-have

- **N1 — Somatic roles (`pon`, `germline_resource`).** Deferred: somatic known-sites have
  their own reference wiring (C4) and the card scopes this slice to germline.
- **N2 — `known_snps_vqsr` / `known_indels_vqsr` / `dbsnp_vqsr` VQSR label capture.**
  VQSR-only resources; deferred (see Out of Scope / Deferred).

## Data Model

`ReferenceIdentity` (`src/contig/models.py:207-218`) gains an optional nested list:

```python
class KnownSiteIdentity(BaseModel):
    role: Literal["dbsnp", "known_indels", "known_snps"]
    path: str | None          # explicit-mode path, or iGenomes asset path
    sha256: str | None        # explicit-mode hash; None for iGenomes / unhashable
    source: Literal["explicit", "igenomes"]
```

- `ReferenceIdentity.known_sites: list[KnownSiteIdentity] | None = None` — absent when no
  flags and non-iGenomes; a non-empty list for the three roles; `None`/`[]` never conflated
  with "not supplied".
- **Back-compat:** purely additive optional field on an already-optional nested model — old
  bundles load with `known_sites = None` (no validator needed; the `sex_inference` idiom,
  `models.py:358-363`).
- **Signature:** extending `ReferenceIdentity` changes `canonical_record_bytes`
  (`signing.py:55-64`) for every record with non-None `reference_identity` — a **disclosed,
  non-narrow signature break** (nearly every real run has non-None identity). This is the
  accepted, house-precedented cost (documented in CHANGELOG + a pinning test), chosen over
  the `LaunchManifest`-only alternative because known-sites *is* reference identity.

## Technical Considerations

- **Params funnel is the single seam.** A param in `params` becomes a `--key value` sarek
  argv (`runner.py:1326-1327`); the only change is what populates `params` (`cli.py:657`).
- **Capture is re-derived, never copied.** `compute_reference_identity(record.parameters)`
  at `_finalize` — a known-sites field follows the same re-derivation; the manifest holds
  the user-supplied spec and `rerun`/`resume` re-feed it (`cli.py:769-791`, `:837-902`,
  `:2509-2572`).
- **iGenomes asset map.** The verified `GATK.GRCh38` block (dbsnp → `dbsnp_146.hg38.vcf.gz`,
  known_indels → `{Mills_and_1000G_gold_standard.indels.hg38,Homo_sapiens_assembly38.known_indels}.vcf.gz`,
  known_snps → `1000G_omni2.5.hg38.vcf.gz`) is the seed; a genome key with no known entry →
  absent, never guessed. Multi-file globs serialize as the path string as-is (path is
  provenance text; no expansion attempt).
- **No real nf-core/sarek in CI** — test-first with tiny synthetic fixtures (injected
  executor, on-disk VCF.gz files), the standing posture of every C5/C2 slice.

## Risks & Open Questions

- **R1 — BQSR blind spot (accepted).** Known-sites consumed by BaseRecalibrator are not
  visible in any VCF header; capturing them requires the user-supplied flags (Option A),
  which this PRD chose. A run whose known-sites were supplied outside Contig records
  nothing — honest `None`, never a guess. (Header-scan capture, Option B, declined by the
  interview.)
- **R2 — Explicit-mode reality.** A Contig `--fasta/--gtf` run today has known-sites all
  `None` unless the user passes the new flags. This slice wires the surface ahead of real
  usage — push, not demand-pull (same tier as the C5 capture slice).
- **R3 — Signature break (accepted, disclosed).** See Data Model. Old signed bundles stop
  verifying; documented + pinned.
- **R3b — Verify-site behavior decided.** `contig verify` / `_signature_status`
  (`cli.py:2264-2281`) will report `signature_ok: False` for every pre-slice signed
  bundle, because `canonical_record_bytes` changed. That is **accepted as-is**: re-signing
  old bundles on verify would be a silent mutation of the tamper-evidence guarantee, worse
  than an honest `signature_ok: False`. The slice states this in the CHANGELOG and pins the
  verify-path behavior with a test (old signed bundle → loads + reports `signed: True,
  signature_ok: False`), so the reproduce integrity claim does not silently regress.
- **OQ1 — Assay gating.** The flags are variant-calling-only in R1. If a future slice wants
  them on somatic (`pon`, `germline_resource`), the role Literal and the assay gate widen
  together. Confirmed as the deliberate narrow first slice.
- **OQ2 — Multi-file serialization.** The iGenomes `known_indels` brace-expanded glob is
  recorded as the single path string, unexpanded. If a real explicit-mode user supplies
  multiple files per role, that's a repeatable-flags follow-on; explicitly not this slice.

## Out of Scope

- **Somatic known-sites** (`pon`, `germline_resource`) — deferred to a C4-linked slice.
- **VQSR label params** (`*_vqsr`) — VQSR-only resources, deferred.
- **Dashboard TS rendering** of `reference_identity` / known-sites — the dashboard carries
  no C5 identity type today; a separate dashboard slice.
- **GTF-version resolution** — blocker-deferred ("no reliable source",
  `CAPABILITY_ROADMAP.md:1199`); not touched.
- **Assembly-signature pre-flight mismatch form** — blocker-deferred (no sample-side signal);
  not touched.
- **Generic nf-core `-p key=value` passthrough** — rejected at the interview; only the three
  typed flags ship.
- **Verdict/exit-code changes** — capture-only, like the C5 capture slice.

## Acceptance (test-first)

Failing tests written before code, per the repo's standing discipline:

1. `compute_reference_identity` with explicit `dbsnp`/`known_indels`/`known_snps` params →
   three `KnownSiteIdentity` entries with real sha256; determinism.
2. A missing/unreadable known-sites file → `sha256 = None`, never a raise, never a
   fabricated hash; the run still finalizes.
3. iGenomes mode → role + asset path, `sha256 = None`, `source = "igenomes"`; the `genome`
   early-return does not drop the known-sites branch.
4. No flags → `known_sites` absent; non-variant assay with flags → refused at pre-flight;
   a missing explicit path → pre-flight **warning** (run proceeds, `sha256 = None`).
5. `LaunchManifest` round-trip: `rerun` and `resume` re-feed the flags; the finalize capture
   is byte-identical across a re-run.
6. `contig methods` and the HTML report render the known-sites rows (explicit hash + iGenomes
   "pipeline-downloaded" phrasing); build naming appears only when the filename/asset map
   carries it.
7. Signature pin: a pre-slice signed bundle loads AND `contig verify` reports
   `signed: True, signature_ok: False` (never a silent regression, never a silent re-sign);
   the break is disclosed in the CHANGELOG.