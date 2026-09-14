# Card: feat/annotation-cache-inputs/aliz

**Source:** inline brief (no GitHub issue — `id` is a slug). Tracker probe:
`gh issue list` shows one open issue, #33 (flaky reproduce freshness guard),
unrelated to this work.

**Owner:** aliz · **Branch:** `feat/annotation-cache-inputs/aliz`
(worktree `.claude/worktrees/feat-annotation-cache-inputs`, branched from
`origin/feat/annotation-cache-wiring/aliz` merged onto `origin/master`)

---

## Brief

C7 follow-on slice: **user-supplied VEP/SnpEff annotation-cache inputs plus a
non-GRCh38 cache guard.** The `annotation-cache-wiring` slice closed C7's
live-cache caveat by injecting `download_cache=true` + `outdir_cache` for both
variant assays, and named this as its own next slice:

> an explicit `--fasta/--gtf` run with a **non-GRCh38** reference would download
> the GRCh38 cache (wrong build) — accepted, with user-supplied
> `--vep_cache`/`--snpeff_cache` paths still a future slice
> — `docs/technical/CAPABILITY_ROADMAP.md:1602-1603`

Scope:

1. **User-supplied cache paths:** wire `--vep_cache`/`--snpeff_cache`
   passthrough into the variant-assay launch params (user values win over the
   auto-download wiring, consistent with the parent slice's setdefault
   contract).
2. **Pre-flight guard:** an auto-downloaded cache is only used when the
   reference is the iGenomes GRCh38 key (`--genome`); a custom
   `--fasta/--gtf` run must carry user-supplied cache paths or get an honest
   refusal — never a wrong-build cache. Keep build detection **flag-based**
   (iGenomes key vs custom fasta), not sequence-inferred: assembly-signature
   inference from sample data is a declared blocker
   (`CAPABILITY_ROADMAP.md:512-516`).
3. **Provenance:** record which cache/build actually ran (user-supplied path or
   auto-downloaded) in `AnnotationProvenance`, consistent with the shipped
   `db_version` capture.

## Honest limits to carry into the writeup

- Parent slice (`annotation-cache-wiring`) is built but **unmerged**; this
  worktree merges it onto master so the code base is current. Its CHANGELOG
  entry already sits under [0.54.0] on master (docs ahead of code); not this
  slice's job to reconcile.
- Push, not demand-pull: no design partner asked; it closes a real
  silent-correctness hole (a wrong-build cache silently mis-annotates a call
  set and defeats the C7 concordance axis).
- No real nf-core/sarek/VEP run in CI — the wiring is pinned by argv/param
  tests, per the parent slice's precedent; real-run smoke stays a manual
  post-merge gate.

## Guardrail check

Layer 2 (run/verify enablement for the shipped C7 annotation assay). No Layer 1,
no wet-lab/clinical dependency, no raw-read egress.