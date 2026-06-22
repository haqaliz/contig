# Add an assay

This is the recipe for teaching Contig a new assay: a curated pipeline plus the
quality checks that verify its output. It is a data change at five mapping
points. There is no engine rewrite: the planner, runner, self-heal loop, and
verifier all read these tables, so adding an assay does not touch any of them.

Contig does NOT generate workflows (that is Layer 1, which we consume). An assay
maps to an ALREADY validated nf-core pipeline, and the verifier scores that
pipeline's MultiQC metrics against a declarative rule pack.

## The five mapping points

Work through these in order. Each is a small, diffable edit; together they make
a goal route to a pipeline and its output get verified.

### 1. Registry entry (`src/contig/registry.py`)

Add a `PipelineEntry` to `REGISTRY` mapping the assay key to a curated pipeline
pinned to a REAL released nf-core tag (check the pipeline's GitHub releases; do
not invent a version):

```python
PipelineEntry(
    assay="myassay",
    pipeline="nf-core/mypipeline",
    revision="1.2.3",  # a real released tag; note the release date in a comment
    description="One line on what the pipeline produces.",
),
```

`_BY_ASSAY` and `_ASSAY_BY_PIPELINE` derive from `REGISTRY`, so `select_pipeline`
and `assay_for_pipeline` pick the new entry up with no further change.

### 2. Match keywords (`src/contig/registry.py`)

Add an entry to `_ASSAY_KEYWORDS` so a free-text goal routes to the assay. These
are lower-cased substring needles; first hit wins, in dict iteration order.

```python
"myassay": (
    "my assay",
    "distinctive-synonym",
    "another-synonym",
),
```

Watch substring ordering and collisions:

- A more specific assay must come BEFORE a more general one whose keyword is a
  substring of it. For example `scrnaseq` is listed before `rnaseq` because
  "scrna-seq" contains "rna-seq", so a single-cell goal would otherwise misroute
  to bulk RNA-seq.
- Avoid short needles that appear inside unrelated words. The `mag` assay uses
  `" mag"` (leading space) and `"mags"` rather than a bare `"mag"` so that words
  like "image" do not route to metagenomics.
- Check the new needles do not collide with an existing assay's. The registry
  tests assert that each goal routes to exactly the intended assay; add a routing
  test for the new assay and a non-collision test against the nearest neighbor.

### 3. Replicate expectation (`src/contig/datashape.py`)

Decide whether the assay's analysis needs biological replicates. Only bulk
differential-expression style assays do (currently just `rnaseq`). If yours does,
add its key to `_REPLICATE_ASSAYS`; otherwise do nothing, because
`assay_expects_replicates` returns `False` for any assay not in that set, and a
single sample raises no replicate warning. Add a datashape test either way so the
decision is pinned.

### 4. Rule pack (`src/contig/verification/rule_pack.py`)

A rule pack is DATA, not code: a list of check dicts the data-driven `evaluate()`
applies to the pipeline's per-sample MultiQC metrics. Each check declares a
metric key and any subset of `{fail_below, warn_below, warn_above, fail_above}`;
the worse status wins, so a check can be a lower bound, an upper bound, or a range.

```python
MYASSAY_RULE_PACK: list[dict] = [
    {
        "check": "human_readable_check_name",
        "metric": "multiqc_metric_slug",  # see the note on slugs below
        "warn_below": 50.0,
        "fail_below": 20.0,
        "message": "what this metric measures",
    },
    # an upper-bound check (lower is better):
    {
        "check": "contamination",
        "metric": "contamination",
        "warn_above": 5.0,
        "fail_above": 10.0,
        "message": "fraction that should stay low",
    },
]
```

Metric keys: use the documented MultiQC general-stats name for the metric. The
exact slug can vary by tool and version, so where you cannot verify the precise
slug, pick the documented quantity's plausible name and leave a comment saying
the slug is unverified (the existing packs do this). Thresholds are illustrative,
tunable engineering defaults for catching a grossly failed run ("ran but wrong"),
not biological or clinical claims; say so in the module comment.

### 5. Wire the pack into `rule_pack_for` (`src/contig/verification/rule_pack.py`)

Add the pack to the `_RULE_PACKS` map so the verifier can select it by assay key:

```python
_RULE_PACKS: dict[str, list[dict]] = {
    ...
    "myassay": MYASSAY_RULE_PACK,
}
```

`rule_pack_for("myassay")` now returns the pack, and an unknown assay still
raises a clear `ValueError`.

## Test the round trip

Add a test that walks the path the CLI walks: goal to assay to pipeline back to
assay to rule pack, and assert the pack fires both a pass and a fail.

```python
def test_myassay_goal_routes_through_registry_to_pack_that_fires_pass_and_fail():
    from contig.registry import assay_for_pipeline, match_assay, select_pipeline
    from contig.verification.rule_pack import evaluate, rule_pack_for

    assay = match_assay("a goal phrase for my assay")
    assert assay == "myassay"
    pipeline = select_pipeline(assay).pipeline
    assert assay_for_pipeline(pipeline) == "myassay"

    pack = rule_pack_for(assay)
    healthy = evaluate({"OK": {"multiqc_metric_slug": 90.0}}, pack)
    assert healthy and all(r.status == "pass" for r in healthy)
    broken = evaluate({"BAD": {"multiqc_metric_slug": 1.0}}, pack)
    assert any(r.status == "fail" for r in broken)
```

Run `uv run pytest` and keep the suite green.

## What you did NOT have to touch

The planner, the runner, the self-heal detect/diagnose/patch loop, the bundle
writer, and the CLI are all assay-agnostic: they consume the registry, the
datashape decision, and the rule pack through the five mapping points above. A
new assay is a data addition, which is the point: the moat is the run-and-verify
engine, and that engine does not grow per assay.

## Worked example: the three assays added together

`methylseq`, `ampliseq`, and `mag` were added by exactly this recipe and are good
references:

- registry entries pinned to real released tags (methylseq 4.2.0, ampliseq
  2.18.0, mag 5.4.2), with keywords (methylation/bisulfite/wgbs;
  16s/amplicon/microbiome/dada2; metagenom/shotgun/mag);
- none added to `_REPLICATE_ASSAYS` (none is a bulk-replicate assay);
- `METHYLSEQ_RULE_PACK` (bisulfite conversion, mapping efficiency, duplication),
  `AMPLISEQ_RULE_PACK` (DADA2 read retention, ASV count, sample read depth),
  `MAG_RULE_PACK` (assembly N50, bin completeness, contamination), each wired into
  `_RULE_PACKS`.
