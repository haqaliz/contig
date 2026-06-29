# PRD: Reference-Identity Provenance

> Capability **C5** (reference & input-data integrity), **slice 1 of N**: capture a
> run's reference identity into provenance so a run can prove which genome and
> annotation it ran against. Captured deterministically, rendered honestly, never
> over-claimed. The pre-flight **mismatch detector** is explicitly a *later* slice.

- **Type:** feat · **Slug:** `reference-identity-provenance` · **Owner:** aliz
- **Branch:** `feat/reference-identity-provenance/aliz`
- **Source:** inline brief (no GitHub issue; handed off from `contig-next`)
- **Roadmap anchor:** `docs/technical/CAPABILITY_ROADMAP.md` → C5

---

## Problem Statement

Contig's reproduce guarantee today pins **tools and parameters** (pipeline +
revision, container digests, Nextflow/Contig versions, input/output checksums) into
`run_record.json` at finalize. It does **not** pin the **reference data** the run
executed against. A run can therefore say "nf-core/sarek @ 3.x, these containers,
these inputs" while leaving silent which genome assembly and annotation produced the
result.

This is the setup for a notorious silent-failure class (`CAPABILITY_ROADMAP.md` C5):
*a run "succeeds" against the wrong genome.* Reference build/annotation mismatch
corrupts results without any error. Today there is nothing in the bundle a
researcher, auditor, or downstream mismatch-detector could check the reference
against.

**Evidence it's real (grounded):**
- `RunRecord` (`src/contig/models.py:235-270`) carries **no** reference fields at
  all — `genome`/`fasta`/`gtf` live only in the `LaunchManifest` reproduce sidecar
  (`models.py:294-296`), as bare paths/keys, **un-checksummed**.
- `compute_input_checksums()` (`bundle.py:61-73`) hashes only sample/FASTQ inputs;
  `fasta`/`gtf` are never added to `input_paths`, so they are never hashed.
- `missing_reference` is already a `FailureClass` (`models.py:185`) with no provenance
  to act on — the later mismatch repair needs captured identity to exist first.

**Cost of the status quo:** the reproduce claim is incomplete (data not pinned), and
the C5 pre-flight mismatch check and the C2 reference/build-mismatch repair are both
blocked because there is no recorded reference identity to compare against.

---

## Goals & Success Metrics

**Goal:** Every run that uses an explicit reference records a verifiable reference
identity in its bundle; every run that uses an iGenomes key records that key
honestly (no fabricated hash). The identity reproduces on re-run and is visible in
the methods paragraph and the provenance panel.

**Success criteria (all testable, all in CI with synthetic fixtures — no real
nf-core run):**
1. An explicit-mode run (`--fasta`/`--gtf`) finalizes with reference identity in
   `run_record.json` containing the SHA256 of the FASTA and the GTF.
2. An iGenomes-mode run (`--genome GRCh38`) finalizes with the genome **key**
   recorded and the checksums marked **unavailable** — and the run never fails
   because the reference could not be hashed.
3. The captured identity is byte-stable across a re-run of the same run on the same
   machine (reproduce guarantee holds).
4. `contig methods` renders a reference-identity clause; the HTML provenance panel
   renders a reference-identity section.
5. A run whose reference files cannot be hashed (missing/unreadable local path)
   degrades gracefully: identity records the path with checksum unavailable, never a
   false/fabricated hash, never a crash.

**Non-metric (moat):** deepens **reproduce** (pins the data, not just tools/params)
and lays the dependency groundwork for the C5 mismatch check + C2 mismatch repair.

---

## User Personas & Scenarios

- **D, biotech researcher / core facility (primary):** needs defensible provenance.
  Scenario: hands a collaborator a bundle; the collaborator must see exactly which
  assembly + annotation (and their checksums) the result was produced against.
- **A, lone computational biologist:** re-runs an analysis months later; wants to
  confirm the reference is the same one as the original run.
- **The engine itself (downstream consumer):** the future C5 pre-flight check and C2
  repair will read this identity to detect/repair mismatches. This slice is their
  prerequisite.

---

## Requirements

### Must-have

1. **Capture reference identity at finalize.** Extend the finalize path
   (`self_heal.py:_finalize`, `bundle.py`) to populate a new structured reference-
   identity field on `RunRecord`, paralleling how `output_checksums` is captured.
   - **Explicit mode** (`--fasta`/`--gtf` known to Contig): record the FASTA and GTF
     identity with `sha256_file()` checksums.
   - **iGenomes mode** (`--genome KEY`): record the key; checksums **unavailable**
     (Nextflow downloads the files; Contig has no local path — confirmed in dig).
2. **Never fail a run over reference hashing.** A missing/unreadable/remote reference
   degrades to "checksum unavailable" with the path/key recorded; never a crash,
   never a fabricated or zero hash, never a false pass.
3. **Reproduce stability.** Captured identity is deterministic and byte-stable across
   a re-run of the same run on the same machine.
4. **Render in `contig methods`.** Add a reference clause to `render_methods()`
   (`methods.py:69-95`) naming the genome/assembly and (explicit mode) the checksums.
5. **Render in the HTML provenance panel.** Add a reference-identity section to the
   provenance panel (`report.py:304-320`), consistent with the existing
   versions/params/checksum tables.

### Should-have

6. Honest empty/absent rendering: a run with no captured identity (e.g. a Snakemake
   run, which skips reference resolution) omits the reference section cleanly rather
   than rendering an empty or misleading table.

### Nice-to-have (explicitly deferred — see Out of Scope)

7. Annotation/GTF **version** string. No reliable source exists; leave null this
   slice rather than fabricate.

---

## Technical Considerations

**Where capture happens.** The dig confirms `_finalize()` (`self_heal.py:703-735`) is
the natural insertion point — it already computes `output_checksums` via
`compute_output_checksums()` and writes the bundle. A new
`compute_reference_identity(...)` in `bundle.py` (paralleling the input/output
checksum helpers, reusing `sha256_file()` at `models.py:17-23`) keeps the pattern.

**Where the reference paths come from.** `resolve_reference()`
(`reference.py:21-41`) already validates and returns the resolved (absolutized)
FASTA/GTF paths or the genome key, with mutual exclusion enforced. The resolved
reference must be threaded to finalize. The `LaunchManifest` already persists
`genome`/`fasta`/`gtf` (`models.py:294-296`), so the raw values are available; the
new work is hashing + structuring them onto `RunRecord`.

**Proposed data model (final shape to be nailed in tech-plan).** A nested model on
`RunRecord`, e.g.:
```
class ReferenceIdentity(BaseModel):
    mode: Literal["igenomes", "explicit"]
    genome: str | None = None          # iGenomes key, mode == "igenomes"
    fasta: str | None = None           # path/basename, mode == "explicit"
    gtf: str | None = None
    fasta_sha256: str | None = None    # None when unavailable (igenomes/missing)
    gtf_sha256: str | None = None
    annotation_version: str | None = None  # null this slice (no fabrication)
# RunRecord gains: reference_identity: ReferenceIdentity | None = None
```
A structured model (vs. stuffing into `parameters`) is preferred so the future
mismatch detector and the renderers read a typed contract. Default `None` keeps
existing fixtures and the Snakemake path valid.

**Reproducibility / verification impact.** This is a reproduce-deepening change: it
adds pinned data identity to the bundle. It does **not** add a verdict or a QC check
(no mismatch adjudication this slice) — so it must not change any existing verdict or
the verify exit code. Determinism is required (same files → same hashes).

**Guardrails (CLAUDE.md / USE_CASE_UNIVERSE):**
- **Layer 2 only** — capture/record + reproduce; no workflow authoring.
- **No raw-read egress** — only hashes/metadata recorded; references are hashed
  locally on the user's compute, nothing leaves the machine.
- **No correctness over-claiming** — capture only; no mismatch *verdict* yet;
  "unavailable" is never rendered as verified.
- **Test-first** — every behavior lands with a failing test first.

**Integration points / files (from dig, likely order):** `models.py` (new model +
field), `bundle.py` (`compute_reference_identity`), `reference.py` (expose resolved
paths/mode if needed), `self_heal.py` / `runner.py` (thread reference into finalize),
`methods.py` (reference clause), `report.py` (provenance section). Mirror tests in
`tests/test_models.py`, `tests/test_bundle.py`, `tests/test_reference.py`,
`tests/test_methods.py`, `tests/test_report.py`.

---

## Risks & Open Questions

- **R1 — Threading the resolved reference to finalize.** `_finalize()` may not have
  the reference in scope today. Risk: a wider plumbing change than expected. Mitigate
  by passing the already-resolved reference (mode + paths/key) through the same
  channel that carries the record to finalize; resolve the exact seam in tech-plan.
- **R2 — Snakemake / no-reference runs.** Reference resolution is nf-core-only
  (`cli.py:371`; Snakemake skips it). `reference_identity` must be optional and absent
  cleanly for those runs (must-have #6).
- **R3 — Hash cost on large FASTAs.** A human genome FASTA is multi-GB; `sha256_file`
  streams in 1MB chunks (cheap memory) but adds finalize wall-time. Acceptable
  (one hash per run, at finalize); note it, don't optimize prematurely.
- **OQ1 — Exact model field names / location** (nested model vs. flat fields) →
  resolve in tech-plan; PRD fixes the behavior, not the identifiers.
- **OQ2 — RO-Crate** export extension is **out of scope** this slice (decided); a
  follow-on can map the identity into the crate.

---

## Out of Scope (explicit)

- **The pre-flight reference/build mismatch detector** (contig-naming / assembly-
  signature comparison). This is the *next* C5 slice and where the real feasibility
  risk lives. This slice only *captures* identity; it issues no mismatch verdict.
- **Known-sites file capture** (dbSNP/gnomA D). Not visible to Contig today (nf-core
  config assets, not CLI params — confirmed in dig). Deferred to its own slice with a
  `--known-sites` CLI design. *(Decision: defer entirely.)*
- **Annotation/GTF version resolution.** No reliable source; left null, not
  fabricated. *(Decision: omit this slice.)*
- **RO-Crate export of reference identity.** Deferred to a follow-on. *(Decision:
  capture + methods + provenance panel only.)*
- **Hashing the actual files Nextflow downloads for an iGenomes key.** Out of Contig's
  namespace; we record the key only.
- **Any QC/verdict change.** This slice does not add a check, move a verdict, or
  change the verify exit code.
