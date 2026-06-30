# Phase 0 findings — determinations spike

## STAR redirect param: `star_index` (live, default)
nf-core/rnaseq and nf-core/scrnaseq (STARsolo) both read a pre-built index via
`--star_index`. The redirect (M12) sets `params["star_index"] = <scratch>`. STAR
build+redirect is the live, default heal path. **In full scope.**

## Classic BWA `bwa index`: non-default → detector+corpus-only this slice
Supported pipelines (registry.py): rnaseq(STAR), sarek(variant_calling),
scrnaseq, methylseq, ampliseq, mag.
- Classic `bwa index` (.amb/.ann/.bwt/.pac/.sa) is reachable ONLY in nf-core/sarek
  with `--aligner bwa-mem`; sarek's DEFAULT is bwa-mem2 (different sidecars +
  loader message, out of scope per PRD).
- methylseq uses bwa-*meth* (`bwameth index`, .bwameth.c2t) — a different tool.
- The detector signature `[E::bwa_idx_load_from_disk] fail to locate the index files`
  is the classic-bwa loader specifically.

**Decision (matches plan rule + pre-approved fallback):** STAR gets full
build+redirect. Classic BWA ships as **detector signature + golden corpus case
only** this slice (Phase 1); BWA build/redirect (Phases 3-4) are deferred. Reason:
no *default* supported pipeline invokes classic `bwa index`; wiring a non-default
aligner's redirect adds surface for little default-path value, and the detector+
corpus case future-proofs cheaply. Follow-on: classic-bwa heal for sarek
`--aligner bwa-mem`.

## Reference at heal time: confirmed in `params`
`params["fasta"]`/`params["gtf"]` are set by `resolve_reference` (cli.py:386) and
`params` is threaded into `_apply_patch_and_maybe_build` (self_heal.py:443). The
STAR deriver reads them directly — M6 needs no manifest spike. Harmonization
(cli.py:396-424) is the scratch-file+param-update precedent to mirror.
