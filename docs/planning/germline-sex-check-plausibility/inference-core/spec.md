# Aspect: inference-core

## Problem slice & outcome

The science + verdict of the slice. A pure module that turns a germline VCF into an
inferred karyotypic sex and a WARN-capped `sex_plausibility` result (+ informational
`x_het_ratio`), reusing `concordance.parse_vcf`. No wiring, no provenance model — those
are separate aspects that consume this one's public functions.

## In scope

- New module `src/contig/verification/sex_plausibility.py`, mirroring
  `verification/variant_metrics.py`'s shape:
  - A frozen `SexSignals` dataclass (`x_het_ratio: float | None`, `x_sites: int`,
    `y_variant_count: int`, `par_masked: bool`, `reference_build: str | None`,
    `inferred_sex: str`), where `inferred_sex ∈ {"XY", "XX", "discordant", "indeterminate"}`.
  - `sex_signals(vcf_path) -> SexSignals` — pure compute:
    - Reuse `parse_vcf` for `{(CHROM,POS,REF,ALT): gt}`.
    - X sites = biallelic sites whose CHROM matches `chrX`/`X` (case-insensitive),
      **excluding PAR by POS** for the detected build.
    - `x_het_ratio` = het / (het + hom-alt + hom-ref non-missing) over X sites — i.e. the
      heterozygous fraction of callable X genotypes. `None` when `x_sites` < `MIN_X_SITES`.
    - Y count = variant sites whose CHROM matches `chrY`/`Y` (case-insensitive), PAR-Y
      excluded.
    - `inferred_sex`: low X-het (`<= X_HET_LOW`) → "XY"; high X-het (`>= X_HET_HIGH`) with
      no Y → "XX"; high X-het **with** Y present → "discordant"; mid-band X-het → "discordant"
      (implausible); `x_het_ratio is None` or no X contig → "indeterminate".
  - `evaluate_sex_plausibility(vcf_path, sample="sample") -> list[QCResult]`:
    - One `sex_plausibility:{sample}` result: PASS ("XY"/"XX"), WARN ("discordant" — message
      names the conflict + causes), UNVERIFIED ("indeterminate", `value=None`, `kind="metric"`).
    - One informational `x_het_ratio:{sample}` result carrying the raw ratio (status the
      established "informational" convention — never WARN/FAIL on its own; if the codebase
      has no info status, emit as `pass` with a clearly-informational message, matching how
      `gene_symbol_concordance` is treated as informational-always-PASS).
- **PAR + build tables** — a small `src/contig/data/` constant or in-module table:
  - GRCh37 chrX length 155,270,560; PAR1 60,001–2,699,520; PAR2 154,931,044–155,260,560.
  - GRCh38 chrX length 156,040,895; PAR1 10,001–2,781,479; PAR2 155,701,383–156,030,895.
  - (Y-PAR coords for M3/N1.) Build detected from `##contig=<ID=chr?X,length=…>`; unknown
    length → `reference_build=None`, `par_masked=False`, unmasked X-het.
  - **Verify these constants against an authoritative source during implementation** — a
    wrong length silently disables masking.
- **Thresholds** in `rule_pack.py` as `SEX_PLAUSIBILITY_PACK` or named constants,
  **confirmed values** (uncalibrated engineering defaults, WARN-capped):
  `X_HET_LOW = 0.10` (≤ → XY), `X_HET_HIGH = 0.20` (≥ → XX; `0.10 < r < 0.20` mid-band →
  discordant/WARN), `MIN_X_SITES = 20` (< → UNVERIFIED), `Y_PRESENT_FLOOR = 5` (≥ non-PAR Y
  variants → Y present). **Not** registered in `_RULE_PACKS`.
- Full unit tests `tests/verification/test_sex_plausibility.py` (see acceptance).

## Out of scope

- `_discover_qc` wiring (aspect verdict-wiring).
- `RunRecord`/provenance/methods/HTML (aspect provenance-surfacing).
- reported-vs-inferred concordance; multi-sample per-sample; FAIL severity.

## Acceptance criteria (testable, tmp_path VCFs, no mocks/network)

- Male-pattern (many low-het chrX sites + several chrY sites) → `inferred_sex=="XY"`,
  `sex_plausibility` PASS, message ~"consistent with XY".
- Female-pattern (autosomal-level het chrX, no chrY) → "XX", PASS.
- Discordant (autosomal chrX het **and** chrY variants) → "discordant", WARN, `!= "fail"`.
- Fewer than `MIN_X_SITES` X sites → "indeterminate", UNVERIFIED, `value is None`.
- No chrX contig at all → "indeterminate", UNVERIFIED.
- PAR sites within a build-detected fixture are excluded from the X-het denominator (assert
  a male fixture whose only "het" X sites are in PAR still reads XY / low ratio).
- Build-undetermined fixture (no `##contig` / unknown length) → `par_masked==False`,
  `reference_build is None`, unmasked ratio, still WARN-capped.
- gzip `.vcf.gz` round-trip == plain `.vcf` result.
- `chrX`/`X` and `chrY`/`Y` both recognized (case-insensitive) — parametrized.

## Dependencies & sequencing

- Depends on: `concordance.parse_vcf`, `models.QCResult`. First aspect — no internal deps.
- Blocks: verdict-wiring and provenance-surfacing both import its public functions.

## Risks specific to this aspect

- Exact PAR/length constants (R2) — pin + assert in tests.
- The "informational" status for `x_het_ratio` — confirm the QCStatus enum during RED;
  fall back to always-PASS-informational if no dedicated info status exists.
