import { test, expect } from "@playwright/test";

import {
  corroboratedByC1Lines,
  corroboratedByC1Text,
  normalMedianVafCheck,
  plausibilityGroups,
} from "../lib/derive";
import type { QCResult } from "../lib/types";

// Unit-level coverage of the C1/C3/C4 surface derivations (C1-4, C3-5, C4-5).
// They run in Node (no `page`) against the pure lib/derive helpers, mirroring
// the reproduce-derive spec: the dashboard READS the engine's qc_results, so
// these pin that a check is surfaced with its recorded status/value/message and
// that UNVERIFIED can never read as corroboration.

function qc(
  partial: Partial<QCResult> & Pick<QCResult, "check" | "status">,
): QCResult {
  return { message: "", value: null, expected_range: null, ...partial };
}

test("C1 lines surface the cross-tool concordance checks, not annotation ones", () => {
  const lines = corroboratedByC1Lines([
    qc({
      check: "genotype_concordance",
      status: "pass",
      value: 0.98,
      kind: "concordance",
      message: "gatk.vcf.gz vs deepvariant.vcf.gz: genotypes agree at 48/50",
    }),
    qc({
      check: "somatic_site_overlap",
      status: "warn",
      value: 0.71,
      kind: "concordance",
      message: "mutect2 vs strelka: 20/28 PASS site(s) agree",
    }),
    // C7 annotation checks belong to corroboratedByLine, not this surface.
    qc({
      check: "consequence_concordance",
      status: "pass",
      value: 0.96,
      kind: "concordance",
      message: "VEP vs SnpEff: 48/50 agree",
    }),
    // A metric check is not concordance.
    qc({ check: "alignment_rate:S1", status: "pass", value: 0.93 }),
  ]);

  expect(lines.map((l) => l.check)).toEqual([
    "genotype_concordance",
    "somatic_site_overlap",
  ]);
  expect(lines[0].label).toBe("gatk.vcf.gz vs deepvariant.vcf.gz");
  expect(lines[1].label).toBe("mutect2 vs strelka");
});

test("an UNVERIFIED C1 check renders as UNVERIFIED, never as corroborated", () => {
  const [line] = corroboratedByC1Lines([
    qc({
      check: "site_overlap",
      status: "unverified",
      value: null,
      kind: "concordance",
      message: "a.vcf.gz and b.vcf.gz share no sites with a known genotype",
    }),
  ]);

  expect(line.status).toBe("unverified");
  expect(line.label).toBe("a.vcf.gz and b.vcf.gz");
  const text = corroboratedByC1Text(line);
  expect(text).toContain("UNVERIFIED");
  expect(text).not.toContain("Corroborated by");
});

test("a corroborated C1 check names its pair and recorded value", () => {
  const [line] = corroboratedByC1Lines([
    qc({
      check: "spearman_concordance",
      status: "pass",
      value: 0.97,
      kind: "concordance",
      message: "salmon.tsv vs featurecounts.tsv: per-gene rank correlation 0.97",
    }),
  ]);
  expect(corroboratedByC1Text(line)).toBe(
    "Corroborated by salmon.tsv vs featurecounts.tsv: spearman_concordance 0.97.",
  );
});

test("the somatic swap check is surfaced with its engine message", () => {
  const message =
    "normal-sample VAF (high => possible tumor/normal swap, mislabel, or " +
    "contamination): median normal-sample variant allele fraction 0.42";
  const found = normalMedianVafCheck([
    qc({ check: "median_vaf:T1", status: "pass", value: 0.3 }),
    qc({
      check: "normal_median_vaf:N1",
      status: "warn",
      value: 0.42,
      message,
    }),
  ]);

  expect(found?.status).toBe("warn");
  expect(found?.value).toBe(0.42);
  expect(found?.message).toBe(message);
  expect(normalMedianVafCheck([])).toBeNull();
});

test("C3 plausibility groups collect their packs and omit absent ones", () => {
  const groups = plausibilityGroups([
    qc({ check: "exonic_fraction:S1", status: "pass", value: 0.8 }),
    qc({ check: "intronic_fraction:S1", status: "warn", value: 0.35 }),
    qc({ check: "sex_plausibility:S1", status: "warn", value: 0.15 }),
    qc({ check: "variant_count:S1", status: "pass", value: 42000 }),
    // A different C3 pack and a non-plausibility metric stay out of these cards.
    qc({ check: "ts_tv_ratio:S1", status: "pass", value: 2.1 }),
    qc({ check: "somatic_variant_count:T1", status: "pass", value: 90 }),
  ]);

  expect(groups.map((g) => g.key)).toEqual([
    "rnaseq_composition",
    "germline_sex",
    "germline_variant_count",
  ]);
  expect(groups[0].rows.map((r) => r.check)).toEqual([
    "exonic_fraction:S1",
    "intronic_fraction:S1",
  ]);
  expect(groups[1].rows.map((r) => r.check)).toEqual(["sex_plausibility:S1"]);
  expect(groups[2].rows.map((r) => r.check)).toEqual(["variant_count:S1"]);

  // A run with none of these checks renders no cards at all.
  expect(
    plausibilityGroups([qc({ check: "alignment_rate:S1", status: "pass" })]),
  ).toEqual([]);
});
