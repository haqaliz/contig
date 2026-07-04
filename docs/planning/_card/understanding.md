# Understanding — feat/somatic-concordance (C1 concordance hook for the somatic assay)

Fast-track Phase-2 dig. Grounded in a full code map (path:line cited inline), confirmed
by direct reads of the modules plus a code-mapping agent pass. No `graphify-out/` graph
exists, so this is from direct reading.

## What the work is really asking

Give the **somatic (tumor–normal)** verdict a cross-tool **concordance** axis (capability
C1 for the somatic assay), corroborating the run's **Mutect2** call set against the
**Strelka2** call set. The premise that makes this the cleanest concordance slice we'll
get: a single sarek somatic run **already emits both** — `default_params={"tools":
"strelka,mutect2"}` (`registry.py:30-34`) injected at dispatch (`cli.py:274-291`,
`cli.py:513-518`). So unlike germline concordance (which needs the user to supply a second
VCF, or Contig to auto-run bcftools via `second_caller.py`), **there is no second tool to
run and no user-supplied input** — both VCFs sit in the bundle under
`variant_calling/<caller>/<tumor>_vs_<normal>/`.

This is squarely Layer 2 / moat ("make every verdict harder to fool"), explicitly named as
the deferred follow-on in three docs: `CAPABILITY_ROADMAP.md:311`, `CHANGELOG.md:44-45`
(v0.14.0), `FEATURES.md:253`.

## The central non-trivial decision (the caveat, now confirmed in code)

**Germline `genotype_concordance` does NOT transfer to somatic.** The germline module
`concordance.py` keys sites on `(CHROM,POS,REF,ALT)` (`concordance.py:40,87-110`) — that
part transfers — but its agreement metric reads the **GT of the first sample column only**
(`_genotype_from_columns`, `concordance.py:113-130`). Somatic breaks this two ways:

1. **Strelka2 somatic SNVs carry no conventional per-sample `GT`** for the tumor; Strelka
   uses fixed `NORMAL`/`TUMOR` column names, not a `##tumor_sample=` header. Mutect2 emits
   GT but the informative sample is the tumor, identified by `##tumor_sample=`
   (`somatic_plausibility.py:59-78`), which is **not** guaranteed to be column 9.
2. So routing somatic through the germline GT path would compare the wrong columns and, for
   Strelka, degrade every site to "unknown GT" → `rate=None` → a blanket UNVERIFIED. Honest,
   but the genotype axis would be dead weight.

**Therefore the honest somatic metric is PASS-site overlap / shared-call fraction** — the
sample-agnostic `site_overlap`-style intersection over `(CHROM,POS,REF,ALT)`, which is
exactly the metric that *is* meaningful cross-caller. This means a **new module**
(`somatic_concordance.py`), not a one-line addition to `_CONCORDANCE_ASSAYS`
(`concordance.py:37`) — the mapping agent reached the same conclusion.

## Affected code (confirmed)

- **New module** `src/contig/verification/somatic_concordance.py` — mirror the shape of
  `concordance.py` / `count_concordance.py`: `kind="concordance"` QCResults
  (`concordance.py:43-58`), WARN-cap thresholds (`concordance.py:30-31`), a
  **min-shared-sites floor** → UNVERIFIED below it (mirror `_MIN_SHARED_GENES=10`,
  `count_concordance.py:41-43`), gzip-open idiom (`concordance.py:79-84`). Its VCF parse
  must be **FILTER-aware** (PASS-only) — net-new, since `concordance.py:parse_vcf` ignores
  the FILTER column entirely.
- **Wiring chokepoint** `runner.py:_discover_qc` somatic branch (`runner.py:78-107`): it
  already locates the Mutect2 VCF by matching `"mutect2"` as a **path component** below the
  run dir (`runner.py:82-93`, avoiding an ancestor-dir false match). Add the **symmetric
  Strelka selector** (`"strelka"` path component) right here, union Strelka's split
  `*.somatic_snvs.vcf.gz` + `*.somatic_indels.vcf.gz` (`tests/test_somatic_end_to_end.py:36-40`),
  and call the new evaluator with both VCFs. This is where somatic concordance runs
  **automatically** — no CLI flag needed, because both inputs are on disk.
- **`run_qc`** (`run_qc.py:83-86`) already appends self-gating concordance evaluators;
  the somatic one can join there or be invoked from `_discover_qc` alongside plausibility.
- **CLI** (`cli.py:709-978`): the germline `--concordance-*` flags and `_resolve_primary_vcf`
  hard-gate to `variant_calling` (`cli.py:905-911`). Because somatic concordance is
  auto-discovered, **no new flag is strictly required**; it surfaces in the verdict/QC
  panel like structural + plausibility. (An optional `contig verify` echo can reuse
  `_echo_concordance`, `cli.py:971-978`, and the never-changes-exit pattern,
  `cli.py:775-787,814-836`.)
- **Structural manifest** (`structural.py:258-261`) needs no change — caller selection is
  by path component downstream, not in the manifest.
- **Model**: no change — reuse `QCResult(kind="concordance")` (`models.py:67-75`);
  `kind="concordance"` already in `QCKind` (`models.py:64`) and grouped by the dashboard.

## Open questions to resolve in the interview (context can't fully settle these)

1. **Auto-run vs explicit flag.** Recommend **auto** in `_discover_qc` (both VCFs already on
   disk; this is the feature's whole point). Germline needed a flag only because the user
   supplied the second set.
2. **Metric set for slice 1.** Recommend **PASS-site overlap / shared-call fraction** as the
   single honest core metric. Tumor-VAF agreement (reusing `somatic_plausibility.py:86-119`)
   is a plausible second metric but adds cross-caller field-alignment complexity — defer it.
3. **FILTER policy.** Recommend **PASS-only** (FILTER == `PASS` or `.`) — somatic VCFs carry
   many filtered candidate calls; comparing raw records would be noisy and misleading.
4. **Strelka split files.** Recommend **union** SNVs + indels into one Strelka call set.
5. **Naming of the emitted checks.** e.g. `somatic_site_overlap` / `somatic_shared_calls`,
   `kind="concordance"`, WARN-capped, UNVERIFIED below the floor.

## Guardrail check (CLAUDE.md)

Layer 2 (verify axis), no Layer-1 authoring. No raw-read egress (operates on VCFs on the
user's compute). Corroboration only — at most WARN, never promotes UNVERIFIED to PASS.
Research-use only, never a cancer diagnosis. Test-first with synthetic two-caller VCF
fixtures (no real nf-core/sarek run in CI), mirroring `test_concordance.py` +
`test_somatic_plausibility.py` fixture style.
