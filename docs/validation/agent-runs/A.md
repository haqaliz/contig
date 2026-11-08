# Persona A — Lone computational biologist

Date: 2026-11-08
Environment: Contig 1.0.0 at `.venv/bin/contig`, commit `c722aa4132589e08316561993f5b87f3b8637df2` (`c722aa4`), macOS 26.5.2 (arm64), zsh. `samtools` 1.24. Repo: `/Users/aliz/dev/at/contig`. Outputs: `/tmp/agent-A/`. The `contig` on PATH is a separate Homebrew install, 0.61.0 (see Blocker 1); all task commands below use the repo checkout.

**Research use only.** Nothing here is a clinical claim or a clinical interpretation.

## Task results

| Task | Command | Exit | Time | Success? | Notes |
|---|---|---|---|---|---|
| Preflight. Default CLI check | `contig variants --help` / `contig readiness --help` / `contig report --help` / `contig ask --help` | 2 (each) | <0.1 s | No | PATH `contig` is 0.61.0 and has none of these commands. `contig report` suggests `export`; the others say “No such command.” See Blocker 1. |
| 1. Variants | `.venv/bin/contig variants tests/fixtures/variants/sample.vcf --clinvar tests/fixtures/variants/clinvar.vcf --iranome tests/fixtures/variants/iranome.tsv --frequencies tests/fixtures/variants/frequencies.tsv --build GRCh37 --gene BRCA1 --out /tmp/agent-A/variants.tsv` | 0 | 0.17 s | Yes | 1 row, 26 columns. BRCA1 `17:43057063 C>CT`, frameshift, ClinVar Pathogenic, Iranome AF 0.001, generic-frequency AF 0.0001. The TSV itself carries no build, source, or filter metadata. |
| 2. Readiness | `.venv/bin/contig readiness --bam data/nfcore/NA12878_sorted_chrM_chr20_rehead_60pdown.cram --bed data/nfcore/target_chr20.bed --caveats data/homology/homology_caveats_GRCh38.bed --out /tmp/agent-A/readiness.tsv` | 0 | 0.77 s | Yes (file); weak answer | 200 targets: 3 `ready`, 4 `caution`, 193 `not-interpretable`. 17 columns. `gene`, `transcript`, and `exon` are empty for every row; `target` is just `20:start-end`. No caveat overlaps (the caveat BED has no chr20 regions). The three `ready` targets are 24, 142, and 31 bases — not genes. No reference FASTA needed for this path. |
| 3. Report | `.venv/bin/contig report r1 --runs-dir tests/fixtures/reporting/runs --variants tests/fixtures/reporting/variants.json --readiness tests/fixtures/reporting/readiness.json --out /tmp/agent-A/report.html --meta /tmp/agent-A/report.json` | 0 | 0.17 s | Yes | 6.0 KB self-contained HTML + 1.2 KB sidecar. 3 variants; readiness 1/1/1. Sidecar has full input SHA-256s and `html_sha256`. The variant table drops most M1 fields (below). |
| 4a. Ask verdict | `.venv/bin/contig ask r1 "What is the verdict?" --runs-dir tests/fixtures/reporting/runs` | 0 | 0.16 s | Yes | `WARN — completed with caveats`; deciding check `library_size_skew`; QC counts 1 pass / 1 warn / 0 fail / 0 unverified; cites `run_record.json` with SHA-256. |
| 4b. Ask GENE3 | `.venv/bin/contig ask r1 "Is GENE3 ready?" --runs-dir tests/fixtures/reporting/runs --readiness tests/fixtures/reporting/readiness.json` | 0 | 0.16 s | Yes | `GENE3: not-interpretable — 0 covered bases`; cites `readiness.json` with SHA-256. Without `--readiness` it correctly says no readiness table is attached and tells you to pass one. |

Commands were timed with `/usr/bin/time -p`; reported time is `real`. The table-writing steps write a research-use notice and a short status line to stderr; `--out` writes the file and prints `Wrote …` to stdout. `ask` writes the answer to stdout and the notice to stderr.

## Limits of this synthetic run

- **The fixtures are not build-consistent.** The task runs the sample VCF as `--build GRCh37`, and the synthetic ClinVar header says `GRCh37`, but the BRCA1 site used here, `chr17:43,057,063`, lies inside the GRCh38 BRCA1 span (chr17:43.04–43.17 Mb), not the GRCh37 span (~41.20–41.28 Mb). The joins succeed because every synthetic fixture uses the same numeric coordinate, not because the build is right. Do not read task 1 as a build-correctness test.
- **The CRAM is a downsampled chr20/chrM subset.** 193/200 target intervals are `not-interpretable` (145 with zero covered bases; the rest below the caution floor), so the 3 `ready` / 4 `caution` counts are properties of this 60pdown input, not a real panel. Do not read task 2 as coverage truth.
- **The report inputs are unrelated to the run.** The run is `nf-core/rnaseq`; the M1 variants are BRCA1/GJB2; the M2 readiness targets are GENE1–GENE3. The report presents them together without warning. This is useful for testing the mechanics, not for any biological conclusion.

## Blockers

1. **The `contig` on PATH is a different, older CLI (0.61.0).** Every research-workbench command in the task script fails with exit 2:

   ```
   $ contig variants --help
   No such command 'variants'.
   $ contig readiness --help
   No such command 'readiness'.
   $ contig report --help
   No such command 'report'. Did you mean 'export'?
   $ contig ask --help
   No such command 'ask'.
   ```

   `contig version` prints `0.61.0`; the repo's `.venv/bin/contig version` prints `1.0.0`. A user following the literal task script has no reason to suspect the binary is stale. Workaround: `.venv/bin/contig` or `uv run contig` (both work). This is a packaging/onboarding blocker, not a missing feature. A version check or a clear “this command requires Contig ≥ …” error would save the first ten minutes.

2. **Readiness cannot answer “which genes are ready?” from the shipped target BED.** `data/nfcore/target_chr20.bed` is BED3 (no name column). The output has the `gene` column, but it is empty for all 200 rows; `transcript` and `exon` are empty too. `target` is only `20:68350-68408`-style coordinates. The command succeeds, but to answer the persona's actual question I must join the BED to a GTF or HGNC table myself. The tool has a `--gtf --genes` path, but the task gives a BED, and the docs do not say a BED3 will produce an unnamed, gene-less readiness table.

3. **The documented CRAM path needs a reference FASTA that is not in the repo.** USAGE 282–284 shows:

   ```
   contig readiness --bam sample.cram --reference GRCh38.fa --bed panel.bed --out readiness.tsv
   ```

   No `GRCh38.fa`/`hg38.fa` exists under `data/` or the repo, and the CRAM header points at `/mnt/appdata/suba/dbasel/hg38.fa`. `samtools view` on the CRAM fails without it:

   ```
   [E::fai_build3_core] Failed to open the file /mnt/appdata/suba/dbasel/hg38.fa : No such file or directory
   ```

   The task's `readiness --bam` command happened to work **without** `--reference` because `samtools depth` only needs alignment positions for this file. That makes the docs worse, not better: the documented command is not reproducible from the checkout, and the undocumented one is. I did not invent or download a reference.

## Confusing output / docs gaps

1. **Generic population frequencies are labelled `gnomad_af` / `gnomad_an`.** With `--frequencies tests/fixtures/variants/frequencies.tsv`, the TSV column is `gnomad_af` and the report column is “gnomAD AF,” but the JSON provenance correctly says `kind: frequencies`, `build: null`. The values come from the generic `CHROM POS REF ALT AF [AN]` file, not gnomAD. This is a source-attribution error in the user-facing table. It also makes `--max-af` semantics source-dependent without saying so.
2. **The default TSV output has no provenance.** `--out variants.tsv` writes only the table: no build, no source paths or hashes, no filter spec. `--json` has all of it (sources, SHA-256s, filters, notes, version). A TSV handed to a PI cannot be reproduced or distinguished from a different filter/source run. The same is true for `readiness --out`: the thresholds (20x/90%/50%) and input hashes exist only in the `--json` sidecar.
3. **Readiness is target-level, not gene-level, and the output does not say so.** With a BED3 the `gene`/`transcript`/`exon` cells are blank, so the table looks like a failed join rather than “this target has no gene annotation.” The summary “3 ready, 4 caution, 193 not-interpretable” counts 200 targets, not genes. The fixture with one target per gene hides this completely.
4. **The 193 `not-interpretable` targets produce no warning.** A 96.5% not-interpretable result is a red flag for a wrong build, wrong sample, or downsampled input. The command prints the counts but does not say “most targets have little or no usable coverage; verify build/sample before interpreting.” A computational biologist will check; a hurried one may conclude the panel failed.
5. **The `caveats` column is blank and ambiguous.** The shipped homology BED covers HBA1/HBA2, PMS2/PMS2CL, SMN1/SMN2 — no chr20 regions — so no overlap is correct. But blank could mean “checked, none” or “not checked,” and neither the TSV nor the summary says which. There is no “caveats checked: none” state.
6. **No build is recorded or checked for readiness.** The readiness JSON sources list path + SHA-256 for the BAM, targets, and caveats, but no build. A GRCh37 BED against a GRCh38 CRAM would simply produce low/zero coverage and a `not-interpretable` row, not a build error. The same is true for the report's M1/M2 attachment: the report sidecar records file hashes, not build compatibility.
7. **The report drops most of the M1 evidence.** The M1 JSON produced by `contig variants --json` contains `rsid`, `qual`, `filter`, `genotype`, `zygosity`, `depth`, `vaf`, `transcript`, `impact`, `hgvsc`, `hgvsp`, ClinVar review status/condition/variant type/HGVS, and allele numbers. The report's variant table is a fixed nine-column view: Gene, Chrom, Pos, Ref, Alt, Consequence, ClinVar significance, “gnomAD AF,” and “Iranome AF.” Even the fixture M1 JSON's `rsid` is dropped. A shareable report without rsid, depth, VAF, genotype, filter, or ClinVar review status is thinner than the table it came from.
8. **The report renders an unannotated variant as a blank row.** In the fixture, the third variant (`1:100 A>G`) shows Chrom/Pos/Ref/Alt and then nothing — no gene, consequence, ClinVar, or frequencies, and no “unannotated” label. The `contig variants` TSV labels such a row `unannotated`; the hand-written fixture M1 JSON uses nulls instead, and the report renders the nulls as blanks. A report should not depend on the producer to avoid a blank row. This looks like a parsing bug or contamination, not “no annotation.”
9. **The report presents unrelated inputs as one coherent document.** The run is `nf-core/rnaseq` (RNA-seq, WARN for `library_size_skew`), the variants are a BRCA1/GJB2 germline panel, and readiness is GENE1–GENE3. There is no compatibility warning, no assay check, and the provenance `Assay` field is blank. The provenance block also says `Signature Unsigned` with no explanation of what signing would add or whether “unsigned” means “failed.” The research-use banner is present, but the document still reads as if the three inputs belong to the same experiment.
10. **“Verified run” + `WARN` is a misleading pair.** The summary says “Verified run r1 … Verdict WARN — completed with caveats.” “Verified” here means the output hashes match the run record. It does not mean the biology is verified. Next to a variant table and a “Pathogenic” ClinVar value, a reader can easily take the wrong meaning.
11. **`ask` suggests commands that do not work in the same context.** The verdict answer suggests `contig show --explain r1` and `contig verify r1` without `--runs-dir tests/fixtures/reporting/runs`. I ran the first one: exit 1, `no bundled run 'r1' in runs`. It also uses `contig` (the stale PATH binary). The GENE3 answer suggests `contig readiness --depth <tsv> --bed <panel.bed> --json --out readiness.json`, with placeholders and no `--caveats`. Suggested actions should be copy-paste runnable with the same context.
12. **SHA-256 display is inconsistent.** The per-section source lines truncate (`8a227322cf3f5542…`), while the “Report inputs” table in the same HTML gives the full 64-character hashes. A reader who copies the source line cannot verify it; a reader who finds the table can. Pick one.
13. **Minor CLI friction.** `contig --version` exits 2 with “No such option”; the correct command is `contig version`. `contig report r1` also does not find the fixture without `--runs-dir tests/fixtures/reporting/runs`; the docs' examples show `contig report r1` without that flag.
14. **Multiallelic VAF is not alt/DP.** On the extra all-variants run, the chr1:200 site has AD `30,20,10`, DP 60, and VAFs 0.4 and 0.25 — i.e. alt/(ref+alt), not alt/DP. That may be intentional, but it is not documented, and `--min-vaf` semantics on multiallelic sites are therefore ambiguous.

## Missing features

1. **Gene-level readiness.** One row per gene with worst state, min/median mean depth, percent at threshold, and the failing exons. Right now 200 target rows are not an answer to “which genes are safe to interpret?”
2. **Automatic gene annotation for BED targets.** If the BED has no name column, join to a GTF/HGNC table (or require the user to supply one) instead of emitting empty `gene`/`transcript`/`exon` columns. A `--by-gene` summary would be the natural output.
3. **Provenance for every output, not only `--json`.** Either always write a sidecar next to `--out`, or add build/source/filter/threshold columns or a header block to the TSV. A bare TSV is not reproducible.
4. **A complete evidence table in the report.** At minimum: rsid, depth, VAF, genotype, filter, transcript, HGVS, impact, ClinVar review status, ClinVar condition, and allele numbers. Make the column set configurable or use the full M1 schema; the current fixed nine-column view hides the evidence a PI needs to judge a variant.
5. **Report input compatibility preflight.** Warn (do not silently accept) when the run assay is RNA-seq and the variants/readiness are a DNA panel, when variant genes and readiness targets do not overlap, when the M1/M2 builds differ, or when the M1 table contains unannotated rows. `report-check` only tells me the inputs are current; it does not flag an assay/gene/build mismatch.
6. **Readiness preflight and build capture.** Warn when a large fraction of targets have zero coverage; record the build of the BAM/CRAM, target BED, and caveat BED; fail or warn on a mismatch instead of reporting it as low coverage.
7. **Explicit caveat status.** Print `caveats checked: none` vs `not checked`, and state which genes the shipped homology/pseudogene BED covers.
8. **A source-aware frequency column and format.** Add a build field to the `--frequencies` TSV, and label the output column by source (`frequencies_af` or the actual source name) instead of `gnomad_af` unless the data really came from gnomAD.
9. **Runnable suggested actions.** Every `ask` action should include the same `--runs-dir`/`--variants`/`--readiness` context, use the working entry point, and avoid placeholders (or clearly mark them as templates).
10. **A shipped reference or a documented reference path for CRAM.** At least a `REF_PATH`/download note and a clear error that names the missing FASTA. The current docs example cannot be run from the repo.

## Quote

“The four commands run in under two seconds once I find the repo's venv, and `ask` gives me the verdict and the GENE3 answer with exact file hashes — that part is clean. But the two artifacts I would actually hand to a PI are thinner than the evidence I started with: the report drops the rsid, depth, VAF, genotype, and ClinVar review status, and the readiness table gives me 200 coordinates with no gene names. I can write the join myself; that is exactly the work I hoped the tool would remove.”

## What I would do next

1. Use `.venv/bin/contig` or `uv run contig`; do not trust the PATH `contig` until the version mismatch is fixed.
2. Keep the M1/M2 `--json` outputs, not just the TSVs, and use them as the report inputs; the TSVs do not carry provenance.
3. Join `target_chr20.bed` to the GRCh38 GTF to label genes, or rerun readiness with `--gtf` + `--genes` if I have a gene list. Treat the 193 `not-interpretable` targets as a data/build check first, not as biology.
4. Before sharing the fixture report, add a methods note that the run is RNA-seq and the M1/M2 tables are unrelated fixtures; better, rebuild it from a DNA run whose assay matches the variant/readiness tables.
5. Ask for the gene-level readiness summary and a report column set that includes rsid, depth, VAF, genotype, filter, transcript, HGVS, and ClinVar review status; those are the first things I would otherwise export and join by hand.
6. Re-check the build of every input against the coordinate spans before interpreting anything; the synthetic fixtures here are not a good build test.
