# Understanding — reference-known-sites-capture

Phase 2 dig note. Grounded in the Phase 1 card (`docs/planning/_card/issue.md`) and
two read-only dig agents over the worktree (branch `feat/reference-known-sites-capture/aliz`):
one mapped the C5 reference-identity machinery, one verified the nf-core/sarek 3.5.1
known-sites surface against the pinned tag's `nextflow_schema.json`/source. All citations
were verified in this worktree unless marked otherwise.

## What the work is really asking

Capture the **known-sites reference resources** a run used (dbSNP, known indels,
panel-of-normals, germline resource) into C5's `ReferenceIdentity` provenance — the next
slice of the least-complete capability. The C5 capture slice (shipped) pins FASTA/GTF
identity + checksums; this pins the second data class, capture-only: no verdict/exit-code
change, rendered in `contig methods` + HTML, round-tripped through `rerun`/`resume`, and
degrading honestly (`None`, never a fabricated hash) exactly like the shipped slice.

## The roadmap premise is STALE — surfaced, not papered over

`CAPABILITY_ROADMAP.md:1197-1198` defers known-sites with *"nf-core config assets, not
CLI params"*. **That is false for sarek 3.5.1, Contig's pinned revision** (`registry.py:27,47`).
The sarek 3.5.1 schema exposes first-class CLI params in group `reference_genome_options`
(and `pon`/`germline_resource` in `variant_calling`): `dbsnp`, `dbsnp_tbi`, `dbsnp_vqsr`,
`known_indels(+tbi/vqsr)`, `known_snps(+tbi/vqsr)`, `pon(+tbi)`, `germline_resource(+tbi)`,
all `default: None`. The config-asset half is real **only in iGenomes mode**:
`conf/igenomes.config`'s `GATK.GRCh38` block wires them to `s3://ngi-igenomes/...`
paths that Nextflow downloads. Verified in sarek `main.nf:37-56` (`getGenomeAttribute`),
`workflows/sarek/main.nf:186-191,512-520,692-721,749-777`.

So the deferral's real shape is: **Contig has no surface** (no CLI flag, no param key, no
passthrough), not "sarek can't expose it". The `--known-sites` design the roadmap asks for
is therefore a genuine CLI/passthrough design, not a "read config assets" design.

## Affected areas (all paths relative to the worktree root)

- `src/contig/models.py:207-218` — `ReferenceIdentity`, optional nested on `RunRecord`
  (`models.py:346`), fields `mode/genome/fasta/gtf/fasta_sha256/gtf_sha256/annotation_version/
  harmonized/harmonized_direction`. Extending it is a **bundle-format + signed-payload change**
  (signing canonicalizes the whole record, `signing.py:55-64`).
- `src/contig/bundle.py:147-180` — `compute_reference_identity(params)`; the capture core,
  called at `_finalize` (`self_heal.py:1715`); re-derived from `record.parameters`, never
  copied. iGenomes early-returns on `genome` (`bundle.py:163-164`) — a known-sites branch
  must not be swallowed by that return.
- `src/contig/cli.py:636-764` — `_dispatch_run` builds `params`; the seams are
  `resolve_reference` (`:657`), `_inject_default_params` (`:462-483`), `_enable_annotation_cache`
  (`:486-513`, the assay-gated setdefault pattern). `build_nextflow_command` serializes any
  param as `--key value` (`runner.py:1326-1327`) — a param in the dict reaches sarek.
- `src/contig/reference.py:21-41` — `resolve_reference`, the only validator (genome vs
  fasta+gtf).
- `src/contig/methods.py:56-79` (`_reference_clause`), `src/contig/report.py:409-428`
  (Reference identity table) — render sites. Dashboard: `reference_identity` is **absent**
  from `dashboard/lib/types.ts` entirely; only surfaced via the parameters table.
- `src/contig/cli.py:769-791` — `LaunchManifest` holds the original genome/fasta/gtf; the
  round-trip mechanism is manifest-holds-spec + re-derive-at-finalize (`rerun` `cli.py:837-902`,
  `resume` `cli.py:2509-2572`). A `--known-sites` value must join the manifest and both
  replay commands.

## Existing known-sites surface: confirmed absence

Grep of `src/contig/` for `dbsnp|known_indels|known_sites|known-sites` matches only a
comment (`models.py:204`, "no known-sites — those belong to later slices"). No flag, no
param key, no model field, no dashboard field. sarek consumes the params in BQSR
(known-sites indels/snps), germline HaplotypeCaller (`--dbsnp` on the GATK command,
`gatk4/haplotypecaller/main.nf:30`), VQSR labels, and somatic Mutect2 (pon +
germline_resource).

## Design options (for the interview)

- **Option A — CLI passthrough (forward + capture):** new flags on `contig run`
  (`--dbsnp`, `--known-indels`, `--pon`, `--germline-resource`, or a generic role=path),
  merged into `params` beside `resolve_reference`; capture in `compute_reference_identity`.
  Honest degradation: absent → `None`; iGenomes → key/path-only with checksum `None`.
- **Option B — read-after-launch (least surface):** once any passthrough exists,
  `compute_reference_identity` picks the keys out of `record.parameters` at `_finalize`
  with zero extra plumbing; and/or scan the run's VCF `##GATKCommandLine` headers (the
  `_pon_status` precedent, `somatic_plausibility.py:307-329`) for `--panel-of-normals`/
  `--germline-resource`/`--dbsnp` paths. Post-hoc; can't see BQSR known-sites.
- **Option C — config-asset table (iGenomes):** teach Contig the iGenomes asset map so a
  `--genome` run records role + s3 asset path, checksum `None` (pipeline-downloaded).
  Records intent/config, not what actually ran; weak alone.

## Ambiguities / open questions for the interview

1. **Does the slice still want a purpose-built `--known-sites` flag, or a generic nf-core
   `-p key=value` passthrough + header capture?** The design was premised on the stale
   "no CLI param exists" claim.
2. **Scope of roles**: germline (`dbsnp`, `known_indels`, `known_snps` — the 3rd is
   VQSR-only 1000G omni) and/or somatic (`pon`, `germline_resource`)?
3. **BQSR blind spot**: BQSR's known-sites are invisible to any VCF header — acceptable
   honest `None`, or does it force Option A/C?
4. **Explicit-mode reality**: a Contig `--fasta/--gtf` run today has known-sites all `None`
   (user never passes them). Is capture demand real yet, or is this wire-before-the-mismatch-
   detector groundwork (C5 dependencies, `CAPABILITY_ROADMAP.md:1194`)?
5. **Multi-file params**: iGenomes `known_indels` is a brace-expanded multi-file glob —
   one entry per file vs. one role entry with a path list?
6. **Signature/bundle cost**: extending `ReferenceIdentity` is a disclosed, non-narrow
   signed-payload break (nearly every real run has non-None identity). Alternative: put
   known-sites on `LaunchManifest` + `params` only (zero signature cost, replay surface).
7. **Checksum semantics**: hash the data VCF.gz only, ignore `.tbi` (recommended, mirrors
   FASTA/GTF)?

## Guardrails check (CLAUDE.md)

Layer 2 (reference-integrity provenance on the reproduce layer) ✓. No Layer 1 ✓. No
raw-read egress (hashes + metadata only) ✓. No correctness over-claiming (checksum `None`,
never fabricated) ✓. Test-first, no real nf-core/sarek in CI ✓. Not a blocker-deferred item —
the GTF-version and assembly-signature siblings stay out of scope by the card.