# Research dashboard data

The `/research` page reads a `manifest.json` from this directory (or
`CONTIG_RESEARCH_DIR`) and renders whatever read-only JSON artifacts are listed.
It never writes or launches anything.

Copy `manifest.example.json` to `manifest.json` and point each field at the JSON
produced by the CLI:

```bash
contig variants sample.vcf --clinvar clinvar.vcf.gz --json --out research/variants.json
contig readiness --depth depth.tsv --bed panel.bed --json --out research/readiness.json
contig report r1 --variants research/variants.json --readiness research/readiness.json \
  --out research/report.html --meta research/report.json
contig family --vcf trio.vcf --ped trio.ped --json --out research/family.json
contig biomarkers --vcf somatic.vcf --callable-bed regions.bed --json --out research/biomarkers.json
contig cohort-build --name "Lab" --variants a.json,b.json --out research/cohort.json
```

The ask panel runs `contig ask` against the manifest's `run_id`, `runs_dir`,
`variants`, and `readiness` (via `CONTIG_CLI` or `uv run contig`).

## Per-run auto-discovery

When no explicit `dashboard/research/manifest.json` (or `CONTIG_RESEARCH_DIR`)
exists, the page picks the newest `runs/<run_id>/research/manifest.json` by
mtime and shows “Auto-discovered from …”. The explicit manifest remains the
default. Paths in a per-run manifest resolve against its own directory first,
then the repo root, so both existing and per-run manifests keep working. The
dashboard never writes or launches a run.
