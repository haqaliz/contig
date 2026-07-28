# Aspect spec: `fail-floor`

Parent PRD: [`../prd.md`](../prd.md). This is the **only** aspect — the slice is one data line
plus the decision record.

## Problem slice and user outcome

A somatic (tumor–normal) run whose Mutect2 step truncated or crashed emits a 0-record VCF. Today
that renders **WARN** and exits `0` even under `--fail-on-verdict` (v0.36.0). After this aspect it
renders **FAIL** and exits `1` under the flag — matching how the germline sibling already treats
the identical failure (`rule_pack.py:84-90`).

## In-scope requirements

- **IS1** — `"fail_below": 1` on the `somatic_variant_count` rule (`rule_pack.py:318-325`).
  `warn_below: 10` and `warn_above: 100000` unchanged. **No `fail_above`.**
- **IS2** — Decision record ("declined by design, not deferred") in three places:
  pack docstrings (`rule_pack.py`), `CAPABILITY_ROADMAP.md` (C3 + C4), `CHANGELOG.md`.
- **IS3** — CHANGELOG must also disclose the signature-invalidation consequence (PRD R2).

## Out-of-scope boundaries

No band on `median_vaf`, `strelka_median_vaf`, `pon_applied`, any RNA-seq or annotation pack. No
CLI/exit-code change. No new model field, `FailureClass`, corpus case, provenance record, or
dashboard card. No change to the signing/canonical-payload contract.

## Acceptance criteria (testable)

| # | Criterion |
|---|---|
| **AC1** | A 0-record somatic VCF → `somatic_variant_count:TUMOR` `status == "fail"`, `value == 0` |
| **AC2** | That same result is **`!= "unverified"`** — a real 0 must not be misread as "couldn't compute" |
| **AC3** | `overall_verdict(results) == "fail"` for that VCF |
| **AC4** | A 2-record set stays `warn` (existing test unchanged); a 12-record set stays `pass` |
| **AC5** | `median_vaf` for the 0-record VCF stays `unverified` (never FAIL, never PASS) |
| **AC6** | The rule declares `fail_below == 1` and **`"fail_above" not in rule`** |
| **AC7** | Somatic bands are well-ordered: `fail_below <= warn_below <= warn_above` |
| **AC8** | `median_vaf` / `strelka_median_vaf` extremes remain `!= "fail"` — WARN-cap tests stay green |
| **AC9** | Full suite green: `uv run pytest` |

## Dependencies and sequencing

None external. `--fail-on-verdict` (v0.36.0) already exists and is untouched. Phases are strictly
ordered: RED → GREEN → docs.

## Open questions or risks specific to this aspect

- The existing `test_variant_count_out_of_band_warns` (`test_somatic_plausibility.py:247-256`)
  uses **2** records; `2 >= fail_below 1`, so it **stays green**. Its comment ("never FAIL") is now
  imprecise for the wrong reason and should be tightened to say *2 is at/above the fail floor but
  below the warn floor*. **Do not delete or invert this test** — it is AC4.
- The 0-record VCF also emits `pon_applied` `unverified` (no GATK header) and `median_vaf`
  `unverified`. `overall_verdict` still reduces to `fail` because a single `fail` dominates
  (`models.py:78-96`). AC3 must assert that, not assume it.
