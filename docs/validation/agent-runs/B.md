# Persona B — Wet-lab scientist who cannot code

Date: 2026-11-08
Environment: Contig 1.0.0, commit `c722aa4132589e08316561993f5b87f3b8637df2` (`c722aa4`), macOS 26.5.2 (arm64), zsh. Repo: `/Users/aliz/dev/at/contig`. Outputs: `/tmp/agent-B/`.

Constraint followed: used only `docs/USAGE.md` and `uv run contig ... --help`; did not read source code. I opened command outputs (BED, TSV, HTML, sidecar) as a user would.

**Research use only.** Nothing here is a clinical claim.

## Task results

| Task | Command | Exit | Time | Success? | Notes |
|---|---|---|---|---|---|
| Read panel/readiness/report docs | `docs/USAGE.md` sections "Panel builder & registry", "Coverage & interpretation readiness", "Research report" | — | — | Yes | Read all three sections. No glossary; many file-format terms guessed (below). |
| Build BRCA1/BRCA2 panel | `uv run contig panel-build --name "Hereditary cancer" --genes BRCA1,BRCA2 --gtf data/ensembl/Homo_sapiens.GRCh38.113.gtf.gz --hgnc data/mane/hgnc_complete_set.txt --version 1 --out-dir /tmp/agent-B/panels` | 0 | 6.94 s | Yes | `hereditary-cancer-a3d15b1d`; 50 exon intervals; 2 MANE transcripts (`ENST00000357654`, `ENST00000380152`); 2.4 KB BED + 525 B JSON. |
| List/show panel | `uv run contig panel-list --dir /tmp/agent-B/panels`; `uv run contig panel-show hereditary-cancer-a3d15b1d --dir /tmp/agent-B/panels` | 0 | <0.2 s | Yes | List is one tab-separated line with no header; show dumps registry JSON. |
| Produce depth TSV for my sample | `samtools depth -a -b panel.bed sample.bam > depth.tsv` | — | — | **No — blocked** | I have no `sample.bam`/`sample.cram` for my sample and no reference FASTA. See Blockers #1. |
| Readiness on shipped fixture (not my sample) | `uv run contig readiness --depth tests/fixtures/readiness/depth.tsv --bed tests/fixtures/readiness/panel.bed --out /tmp/agent-B/readiness-fixture.tsv` | 0 | 0.16 s | Yes (tool only) | 4 targets: 2 `ready`, 1 `caution`, 1 `not-interpretable`. Targets are `GENE1`–`GENE4`; not my genes, not my data. |
| Readiness with my panel + fixture depth (mechanical check) | `uv run contig readiness --depth tests/fixtures/readiness/depth.tsv --bed /tmp/agent-B/panels/hereditary-cancer-a3d15b1d.bed --out /tmp/agent-B/readiness-panel-smoke.tsv` | 0 | 0.16 s | Partial (not my sample) | My BED was accepted (50 targets). Fixture depth has only chr1, so 50/50 came out `not-interpretable`; this is not a BRCA coverage result. |
| Readiness `--bam` with repo CRAM (not my sample) | `uv run contig readiness --bam data/nfcore/NA12878_sorted_chrM_chr20_rehead_60pdown.cram --bed /tmp/agent-B/panels/hereditary-cancer-a3d15b1d.bed --out /tmp/agent-B/readiness-bam-attempt.tsv` | 0 | 0.66 s | Partial (not my sample) | Tool path works. The CRAM is a chr20/chrM subset, so 50/50 `not-interpretable`; not my sample. |
| Build report | `uv run contig report r1 --runs-dir tests/fixtures/reporting/runs --variants tests/fixtures/reporting/variants.json --readiness tests/fixtures/reporting/readiness.json --out /tmp/agent-B/report.html --meta /tmp/agent-B/report.json` | 0 | 0.16 s | Yes | 5.9 KB self-contained HTML + 1.2 KB sidecar. 3 variants; readiness `ready`/`caution`/`not-interpretable` = 1/1/1. |
| Check report inputs | `uv run contig report-check /tmp/agent-B/report.json` | 0 | 0.16 s | Yes | All three inputs "current": run record, variants, readiness. |

Limits of this run: I never produced a depth file for BRCA1/BRCA2. Every readiness number above comes from shipped fixture data or a chr20/chrM CRAM. Do not read any of them as coverage for my panel.

## Blockers

1. **Readiness needs an aligned read file; I only have a VCF.** `contig readiness --help` and USAGE 287–289 say the input is either a `samtools depth -a` TSV or a BAM/CRAM. The documented way to make the TSV is:

   ```bash
   samtools depth -a -b panel.bed sample.bam > depth.tsv
   ```

   then, from USAGE:

   ```bash
   contig readiness \
     --depth depth.tsv \
     --bed panel.bed \
     --caveats homology_caveats_GRCh38.bed \
     --out readiness.tsv
   ```

   I cannot run the first command: I have no `sample.bam`/`sample.cram` and no `GRCh38.fa`. The documented alternative also needs files I do not have:

   ```bash
   contig readiness --bam sample.cram --reference GRCh38.fa \
     --bed panel.bed --out readiness.tsv
   ```

   The repo's only CRAM is a chr20/chrM subset (`NA12878_sorted_chrM_chr20_rehead_60pdown.cram`); the other BAMs are MSI/RNA-seq examples, not a germline DNA BAM/CRAM for my sample. None is a valid readiness input for my BRCA panel. So I cannot answer the question I came for: which of my genes are safe to interpret.

   This is a data absence, not something the CLI can fix. The docs fix is to say **up front** that a VCF is not enough for readiness, and to give the exact thing to request from the sequencing provider: an aligned BAM/CRAM in the same build, or a `samtools depth -a -b` file over the panel BED. USAGE currently only shows the command; it never says "you need the BAM, not the VCF."

## Confusing output / docs gaps

1. **Readiness is per exon, not per gene.** My panel is 2 genes / 50 exon targets. The summary says `50 target(s): ...` and the table has 50 rows, with `target` and `gene` both showing `BRCA1`/`BRCA2`, and `transcript`/`exon` blank. The question "which genes are safe to interpret?" has no gene-level answer. I would have to aggregate 50 rows myself. The fixture (one target per gene) hides this problem completely.
2. **No glossary or file-format primer.** BED, GTF, BAM, CRAM, FASTA, HGNC, MANE, sidecar, M1/M2, and checksum are all used as if I already know them. See the terms table below.
3. **BED columns and coordinates are under-documented.** USAGE says BED is `chrom start end [name]`; the panel-build BED has six columns: `chrom start end gene gene transcript`. The 5th/6th columns are not explained, and readiness ignores them (`transcript` is blank in the output). I also cannot tell whether BED starts are 0-based or 1-based, which matters if I compare exon coordinates to a paper.
4. **Build matching is never warned about.** `--build` defaults to `GRCh38`. Nothing says the panel, BAM/CRAM, VCF, GTF, and annotation must all be the same build. My lab has GRCh37 samples; a silent GRCh38 panel would be wrong and I would not see an error. This is the most dangerous docs gap I found.
5. **`--bam` / `--reference` is under-explained.** I do not know what a CRAM is, why it needs a FASTA, or where to get `GRCh38.fa`. I ran the repo CRAM without `--reference` and it worked, which made the flag more confusing, not less. The docs say `--reference` "is passed for CRAM decoding" but never explain the failure mode or the build match.
6. **`samtools` is missing from Prerequisites.** USAGE lists Nextflow, Java, Docker. The readiness manual command and the `--bam` path both need `samtools`; help says the binary defaults to `samtools`. A non-coder will not know to install it, check it, or what version.
7. **No starting point for the reference files.** The panel example uses `Homo_sapiens.GRCh38.113.gtf.gz` and `hgnc_complete_set.txt` as if I already have them. USAGE does not say they come from Ensembl/HGNC, which release, or that the GTF may be gzipped. The repo has copies under `data/`, but an external user does not.
8. **`M1` / `M2` are unexplained.** USAGE and `--help` call variants "M1" and readiness "M2"; the report sidecar repeats the labels. I guessed they are milestone numbers. They mean nothing to a wet-lab reader.
9. **`sidecar` / `--meta` are unexplained.** The report docs say "JSON sidecar"; the flag is `--meta`. I guessed it is the companion metadata JSON. A one-line definition would remove the guess.
10. **The report example assumes `r1` is discoverable.** USAGE shows `contig report r1`; it does not mention `--runs-dir`, which I had to find in `--help`. For a non-coder, "where is `r1`?" is not obvious.
11. **Unannotated variant becomes a blank row, not `unannotated`.** USAGE 244–245 promises a variant without VEP/SnpEff is "shown as `unannotated`, never dropped." The report's third variant row is blank: `chrom 1`, `pos 100`, `A>G`, with no gene, consequence, ClinVar, or frequency. In a BRCA1/BRCA2 report that looks like contamination or a parsing bug, not an unannotated record.
12. **The fixture report mixes assays with no warning.** The run is `nf-core/rnaseq` (RNA-seq, verdict WARN for `library_size_skew`), the variants are BRCA1/GJB2, and the readiness targets are GENE1–GENE4. Nothing warns that the attached tables are unrelated to the run or to each other. A non-coder cannot tell whether this is expected test data or a mis-attached file. `report-check` only checks hashes, not gene/assay compatibility.
13. **"Verified run" vs a WARN verdict.** The report says "Verified run r1 ... Verdict WARN — completed with caveats". "Verified" means the output hashes match the record, not that the biology is verified. A wet-lab reader can easily read "Verified" as "trustworthy". The research-use banner helps, but the wording still misleads.
14. **"Deciding checks: library_size_skew" / "Skew 2.1" is opaque.** The report gives a value and an "expected" column but no units or threshold; I do not know what 2.1 means or how close it is to the line. (QC readability, not biology.)
15. **`panel-list` has no header.** The line `hereditary-cancer-a3d15b1d  1  Hereditary cancer  genes  BRCA1,BRCA2  GRCh38` is guessable only because I just built it; `panel-show` supplies the labels.
16. **Provenance shows `Assay` blank and `Signature Unsigned`.** No explanation in the report. "Unsigned" can read as "failed" rather than "not signed". USAGE explains signing, but the report does not link it.
17. **The HTML truncates SHA-256.** The report shows `8a227322cf3f5542…`; USAGE says each section names its source file and SHA-256. The full hash is only in the sidecar, so the HTML alone cannot be checked.
18. **`--caveats` gives no guidance for BRCA1/BRCA2.** The shipped homology BED covers SMN1/SMN2, PMS2/PMS2CL, HBA1/HBA2. I do not know whether BRCA1/BRCA2 have pseudogene/homology caveats, whether to pass the BED anyway, or what a blank `caveats` column means: "checked, none" or "not checked". The docs say a caveat overlap makes a target `caution`, but not how to decide for genes outside the shipped list.
19. **Readiness output columns are not fully documented.** The table adds `target`, `gene`, `transcript`, `exon`, `bases`, `covered_bases`, `zero_bases`, `caveats`, and `reason`; USAGE lists only the metrics. I guessed the rest. With a BED input, `transcript`/`exon` are blank and `target`/`gene` duplicate, so the output looks emptier than the panel I just built.
20. **Readiness summary counts targets, not genes.** "2 ready, 1 caution, 1 not-interpretable" is four genes only because the fixture has one target per gene. With my panel it is 50 targets; the count cannot be read as genes. Same root cause as #1.

## Terms I had to guess

| Term | Where it appears | What I guessed | What was missing |
|---|---|---|---|
| BED | Panel builder, readiness, report | A plain-text table of genomic regions: chrom, start, end, name | Definition, 0-based vs 1-based, whether extra columns are allowed, what the 5th/6th columns mean |
| BED4 / 8-column caveat BED | `readiness --help` for `--caveats` | A BED with 4 columns, or a special 8-column caveat format | What "BED4" means and where the 8-column schema is defined |
| GTF | `panel-build --gtf` | A gene/exon annotation file from Ensembl | Definition, source, release/build, whether `.gz` is accepted |
| HGNC | `panel-build --hgnc` | A gene-symbol authority list used to fix old/alias names | Where to get it, whether it is required, what changes without it |
| MANE Select | Panel builder docs/help, panel JSON | The "canonical" transcript per gene | What MANE is, why one transcript is preferred, what happens with `--transcripts all` |
| BAM | Readiness docs/help | An aligned-reads file from the sequencer/aligner | Definition, how to get one, that it must be sorted/indexed and build-matched |
| CRAM | Readiness docs/help | A compressed aligned-reads file | Definition, why `--reference` is needed, how it differs from BAM, where the FASTA comes from |
| FASTA / `GRCh38.fa` | `readiness --reference` | The reference genome sequence | Definition, source, build match, that CRAM decoding needs it |
| `samtools depth -a -b` | Readiness docs | A tool that computes per-base coverage; `-a` all positions, `-b` BED | That samtools must be installed, BAM sorted/indexed, and what `-a`/`-b` do |
| Depth TSV | Readiness docs/help | A table of `chrom pos depth` (docs do define this as 1-based) | A sample file and a pointer to one; how it relates to BAM/CRAM |
| Sidecar / `--meta` | Report docs/help | Companion JSON with input hashes | Definition of "sidecar"; why `--meta` rather than `--json` |
| M1 / M2 | Report docs/help, sidecar notes | Milestone labels for variants and readiness | What M1/M2 stand for; why the labels leak into user output |
| SHA-256 / checksum | Panel meta, report, report-check | A file fingerprint | Whether I must verify/copy it, and why the HTML truncates it |
| Build / GRCh38 | `--build` default, panel meta | Genome assembly version | That every input must match; what happens on mismatch |
| ENST transcript ID | `panel-show` JSON | An Ensembl transcript accession | Gene-to-transcript mapping; which one is MANE Select and why |
| "Deciding checks" | Report | The QC checks that set the verdict | Definition; which checks count and why |
| Homology/pseudogene caveat | Readiness docs/help | Regions where reads mis-map between similar genes | Whether my genes have any; what an empty caveats column means |
| AF | Report columns (`gnomAD AF`, `Iranome AF`) | Allele frequency | Definition/units; the docs explain sources but not the abbreviation |
| "Verified run" | Report summary | I first read it as "the biology is verified" | It means output hashes match the run record; the WARN verdict contradicts the plain reading |
| "Assay" | Report provenance | The type of sequencing run | Why it is blank, and whether that matters |

## Missing features

1. **Gene-level readiness summary.** The direct answer to "which genes are safe to interpret": one row per gene with worst state, min/median mean depth, percent at threshold, and the failing exons. This is the top missing feature for this persona; 50 exon rows are not an answer.
2. **Readiness preflight / input checklist.** Before running, check BAM/CRAM (sorted, indexed), reference FASTA, build, and BED, and print the exact missing file and who to ask for it. If the user passes only a VCF, say explicitly "readiness cannot use a VCF" and show the `samtools depth` command or the BAM/CRAM ask.
3. **Report compatibility warnings.** Warn (not fail) when the run assay does not match the attached tables, when variant genes do not overlap readiness targets, or when an attached table has unannotated/blank rows. This would have caught the fixture's RNA-seq + BRCA/GENE1–4 mix.
4. **Human-readable panel summary.** `panel-show` could print gene, exon count, transcript(s), and genomic span before the JSON; `panel-list` could have a header. Optional, but it is the difference between "I built the right panel" and "I hope so."
5. **Glossary and a "files you need for each command" page.** One page covering VCF, BED, GTF, HGNC, BAM, CRAM, FASTA, depth TSV, sidecar, M1/M2, and build. This is the highest-leverage docs fix after the readiness blocker.
6. **A toy readiness example in USAGE.** A tiny depth TSV + tiny panel BED, with the expected table, so a non-coder can see the output before owning a BAM. The repo already has `tests/fixtures/readiness/`; USAGE never points to it.
7. **Explicit caveat status.** Print `caveats checked: none` vs `not checked` rather than a blank column, and say which genes the shipped caveat BED covers.
8. **"Hash-verified" wording in the report.** Replace or qualify "Verified run" so it cannot be read as biological verification.
9. **`readiness --by-gene` / gene summary output file.** Same as 1, as a concrete flag rather than only a display change.

## Quote

"I have the VCF the sequencing company sent me and a list of genes. Contig built a clean BRCA1/BRCA2 panel in seven seconds, then stopped: to tell me whether the genes are safe to interpret it needs a BAM/CRAM I was never told to ask for. The docs explain the commands, not the files. And even with a depth file, it would hand me 50 exon rows for two genes and no gene-level answer."

## What I would do next

1. Ask the sequencing provider for the aligned BAM/CRAM in GRCh38, or a `samtools depth -a -b` file over my panel BED; get the build confirmed in writing.
2. Rerun `contig readiness` with the real depth, my panel BED, and the shipped caveat BED; treat any gene that comes out `not-interpretable` as "do not interpret" and any `caution` as "ask the PI."
3. Ask for a gene-level summary; until it exists, export the 50-row TSV to Excel and pivot by gene/state. That is slow and easy to get wrong, which is exactly why I want the feature.
4. Build the real report with the verified run, real variants, and real readiness; before sending it to the PI, confirm the run assay actually matches the panel. The fixture mixes RNA-seq with a cancer panel and I cannot tell whether that is a test artifact or a real compatibility gap.
5. Ask for the glossary and the files-needed page; I do not want to guess BED, CRAM, FASTA, and M1/M2 again.
