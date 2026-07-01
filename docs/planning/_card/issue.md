# Card: feat self-heal-bwa-mem2-index

- **Type:** feat · **Owner:** aliz · **Branch:** `feat/self-heal-bwa-mem2-index/aliz`
- **Source:** no GitHub issue — **inline brief** handed off from `contig-next` (2026-07-01).
- **Capability:** C2 (self-heal breadth) — the next aligner-index kind on the shipped
  `IndexBuilder` seam, after the STAR directory-index slice (v0.10.0).

## Brief (from the contig-next handoff)

Extend the C2 `IndexBuilder` self-heal seam (shipped through v0.10.0 for STAR
directory indexes and the single-file `.fai/.bai/.tbi/.csi/.dict` family) to a
missing/incompatible **bwa-mem2** aligner index on an nf-core/sarek run, since sarek
defaults to bwa-mem2 and is the live redirect target that classic BWA lacked. Reuse
the suffix-strip deriver (bwa-mem2 is sidecar-file-shaped beside the FASTA, not
directory-shaped like STAR), add the net-new bwa-mem2 failure signature to the
detector plus one golden corpus case, and record `built_index_and_retried` with
honest `index_unresolvable`/`index_build_failed` give-ups — all test-first with an
injected builder, no real bwa-mem2 in CI.

## ⚠️ Caveat to dig on FIRST (the key feasibility/design risk)

**Does a bwa-mem2 missing-index failure actually surface at runtime, or does
nf-core/sarek silently auto-build a missing index?** Phase 2 must resolve this before
any PRD work:

1. **If sarek auto-builds a fully-missing index**, then the recoverable live case is a
   **user-supplied incompatible/partial/corrupt** bwa-mem2 index (mirroring STAR's
   shipped *version-incompatible* path, which is the robust live case with iGenomes /
   user-supplied indexes). Scope the slice to that case.
2. **Confirm the exact bwa-mem2 runtime error string** for the detector — it is
   net-new; no bwa-mem2 signature exists in `src/` today (classic BWA's
   `[E::bwa_idx_load_from_disk]` is detector-only). It must be narrow enough not to
   swallow a wrong-reference masquerade.
3. **Confirm the bwa-mem2 sidecar set**: `.0123 / .amb / .ann / .bwt.2bit.64 / .pac`
   beside the FASTA — distinct from classic BWA (`.amb/.ann/.bwt/.pac/.sa`) and **NOT
   interchangeable**. The success check is "all bwa-mem2 sidecars present + non-empty".

## Pre-dig facts (confirm in Phase 2)

- v0.10.0 shipped STAR directory-index build+redirect and **deferred** "bwa-mem2 index
  set + aligner-mismatch heal"; classic BWA is detector+corpus-only because "no default
  supported pipeline invokes classic `bwa index`" — `CHANGELOG.md` 0.10.0,
  `docs/technical/CAPABILITY_ROADMAP.md:149-158`.
- bwa-mem2 IS the live target: nf-core/sarek defaults to it —
  `docs/planning/self-heal-dir-index/understanding.md:37-38`.
- bwa-mem2 is sidecar-file-shaped (FASTA = index path minus suffix → the existing
  `_strip_suffix` deriver reuses, unlike STAR which needed reference-threading) —
  `understanding.md:37-43`.
- Build table is `{ext: (derive_source, build_argv)}`; outcomes `built_index_and_retried`
  / `index_unresolvable` / `index_build_failed`; build-once-per-path guard bounds the loop.

## Why this was picked (contig-next ranking)

- The genuinely-unblocked next slice of the just-shipped v0.10.0 work: classic BWA was
  deferred only for lack of a live target, and bwa-mem2 supplies exactly that (sarek
  default). Rule 6 (follow-on of shipped work) + rule 4 (unblocked, clear testable slice).
- Highest moat-leverage: C2 is "the most directly gets-better-with-better-models surface
  and the richest corpus fuel" (`CAPABILITY_ROADMAP.md:160-166`); a recovered failure
  raises unattended-completion (Phase-1 headline metric) and seeds a golden corpus case.

## Open questions for the interview

- **Missing vs incompatible/partial:** which bwa-mem2 index states does the slice heal
  (fully-missing, version/format-incompatible, partial)? Depends on caveat #1.
- **Reference threading:** bwa-mem2's FASTA comes from suffix-strip, so it should NOT
  need the STAR reference-threading plumbing — confirm the deriver signature suffices.
- **Aligner-mismatch (classic-bwa vs bwa-mem2):** in or out of this slice? (Deferred by
  the v0.10.0 note; likely out.)
- **Corpus seed:** reuse the `missing_index` `FailureClass` (rebuild is the heal) vs a
  new member — leaning reuse, mirroring STAR.

## Guardrails (CLAUDE.md) — clean

- **Layer 2 only** (self-heal/execution). No Layer-1 drift.
- **No raw-read egress** — index built locally from the user's FASTA.
- **No correctness over-claiming** — build only when the source FASTA resolves; honest
  give-up (`index_unresolvable`/`index_build_failed`); never a false pass.
- **Test-first** — injected `IndexBuilder`/executor fixtures; no real bwa-mem2 in CI.

## Out of scope (deferred — do not drift)

- Classic-BWA build/redirect (no live target); the classic-vs-mem2 **aligner-mismatch**
  heal; corrupt/partial STAR index signature; BAM/CRAM `.csi`; peak-RSS scaling.
- Assembly-signature reference mismatch (no sample-side contig signal).
- Building Layer 1 (NL → workflow) — not the product.
