# A tiny example Snakemake workflow for Contig's round-trip test (PRD contract B).
# Two rules so the stats JSON carries more than one rule: `align` writes a file
# and `count` consumes it. The workflow is deliberately trivial (it touches
# files, no real tools) so the engine-adapter round-trip can run anywhere without
# bioinformatics dependencies. A real assay Snakefile slots in unchanged.

rule all:
    input:
        "counts.tsv"

rule align:
    output:
        "aligned.bam"
    shell:
        "echo aligned > {output}"

rule count:
    input:
        "aligned.bam"
    output:
        "counts.tsv"
    shell:
        "echo 42 > {output}"
