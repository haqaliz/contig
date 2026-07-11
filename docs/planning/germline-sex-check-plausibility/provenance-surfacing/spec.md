# Aspect: provenance-surfacing

## Problem slice & outcome

The inferred karyotypic sex + its evidence becomes durable provenance: captured on the
RunRecord, rendered in `contig methods` and the HTML report, and round-tripped through the
reproduce bundle with back-compat. Mirrors the C5 `ReferenceIdentity` / `AnnotationProvenance`
pattern.

## In scope

- **Model:** a new `SexInference` pydantic model in `src/contig/models.py`:
  `inferred_sex: str`, `x_het_ratio: float | None`, `x_sites: int`, `y_variant_count: int`,
  `par_masked: bool`, `reference_build: str | None`. Add `sex_inference: SexInference | None
  = None` to `RunRecord`. The `= None` default + a lenient load keeps **pre-slice bundles
  loading and reproducing** (assert with a legacy-bundle fixture).
- **Capture** at `_finalize` (the same place `AnnotationProvenance`/`ReferenceIdentity` are
  attached), **gated to `assay == "variant_calling"`** (germline only; every other assay
  leaves it `None`). Derive from the same `sex_signals(vcf)` compute the inference-core
  aspect exposes — locate the VCF exactly as the QC path does; absent VCF → `None`, never
  fabricated.
- **Render:** a `contig methods` section line (e.g. "Inferred karyotypic sex: XY
  (X-heterozygosity 0.02 over 143 non-PAR sites, GRCh38; Y variants present)"; "undetermined"
  when indeterminate) and an HTML provenance-panel entry. Honest labelling: research-use
  inference, never a clinical determination; state `par_masked=false`/build-undetermined when
  applicable.
- **Reproduce round-trip:** the field is written into and re-loaded from the bundle
  (`write_bundle`/load), asserted by a round-trip test; legacy bundle → `None`.

## Out of scope

- The inference math (aspect inference-core) and the QC-verdict wiring (aspect
  verdict-wiring). This aspect **consumes** `sex_signals`.
- S1 dashboard card is **should-have**: implement only if the aspect lands with time to
  spare; it reads the captured `SexInference` (no engine recompute). Not required for
  aspect acceptance.

## Acceptance criteria (testable)

- A `variant_calling` RunRecord finalized with a male-pattern VCF carries a `SexInference`
  with `inferred_sex=="XY"`; a non-germline assay carries `sex_inference is None`.
- `contig methods` output for that record contains the inferred-sex line; an indeterminate
  record renders "undetermined" (no fabricated call).
- HTML report contains the sex-inference provenance entry.
- Round-trip: write a bundle with `SexInference`, reload → equal; load a **pre-slice** bundle
  (no `sex_inference` key) → loads, field is `None`, reproduces.
- Full suite green: `uv run pytest`; if S1 built, `npm run build` in `dashboard/`.

## Dependencies & sequencing

- Depends on: **inference-core** (`sex_signals`/`SexInference` fields). Sequence after it.
- Independent of verdict-wiring; can proceed in parallel with it once inference-core lands.

## Risks specific to this aspect

- **Back-compat** is the sharpest risk: a new non-defaulted RunRecord field would break
  loading old bundles. Default `None` + a load test with a legacy fixture is mandatory (RED
  first).
- Duplicate VCF discovery: reuse the same locate logic as `_discover_qc` to avoid a second,
  divergent path (a helper shared with verdict-wiring is acceptable).
