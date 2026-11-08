// Read-only access to the research-workbench JSON artifacts. The dashboard reads
// a small manifest from CONTIG_RESEARCH_DIR (default dashboard/research) and
// renders whatever tables are attached; it never writes or launches anything.
import "server-only";

import { promises as fs } from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";

const pexec = promisify(execFile);

export interface ResearchManifest {
  run_id?: string;
  runs_dir?: string;
  variants?: string;
  readiness?: string;
  report_meta?: string;
  report_html?: string;
  family?: string;
  biomarkers?: string;
  cohort?: string;
}

export interface VariantRow {
  key?: { chrom?: string; pos?: number; ref?: string; alt?: string };
  rsid?: string | null;
  gene?: string | null;
  consequence?: string | null;
  impact?: string | null;
  genotype?: string | null;
  zygosity?: string | null;
  depth?: number | null;
  vaf?: number | null;
  filter?: string | null;
  clinvar_significance?: string | null;
  clinvar_review_status?: string | null;
  population_af?: number | null;
  gnomad_af?: number | null;
  iranome_af?: number | null;
}

export interface VariantTable {
  meta?: { generated_at?: string; filters?: Record<string, unknown>; sources?: unknown[] };
  variants: VariantRow[];
}

export interface ReadinessTarget {
  target?: { name?: string; gene?: string; transcript?: string; exon?: string; chrom?: string; start?: number; end?: number };
  bases?: number;
  covered_bases?: number;
  mean_depth?: number;
  pct_20x?: number;
  pct_50x?: number;
  pct_100x?: number;
  zero_bases?: number;
  caveats?: string[];
  readiness?: string;
  reason?: string;
}

export interface ReadinessGene {
  gene: string;
  targets: number;
  bases: number;
  covered_bases: number;
  mean_depth: number;
  pct_20x: number;
  pct_50x: number;
  pct_100x: number;
  zero_bases: number;
  caveats: string[];
  readiness: string;
  reason: string;
}

export interface ReadinessTable {
  meta?: { thresholds?: Record<string, number>; notes?: string[]; generated_at?: string };
  targets: ReadinessTarget[];
  genes?: ReadinessGene[];
}

export interface ReportMeta {
  run_id?: string;
  generated_at?: string;
  contig_version?: string;
  spec?: { title?: string; subtitle?: string; author?: string; institution?: string; template?: string };
  inputs?: { kind: string; path: string; sha256: string; note?: string }[];
  html_sha256?: string;
  notes?: string[];
}

export interface FamilyRow {
  family_id?: string;
  child?: string;
  key?: { chrom?: string; pos?: number; ref?: string; alt?: string };
  gene?: string | null;
  consequence?: string | null;
  child_gt?: string | null;
  father_gt?: string | null;
  mother_gt?: string | null;
  inheritance?: string;
  mendelian_consistent?: boolean | null;
  de_novo_candidate?: boolean;
}

export interface FamilyTable {
  meta?: { family_id?: string; samples?: string[]; summary?: Record<string, unknown> };
  rows: FamilyRow[];
}

export interface BiomarkerEntry {
  name: string;
  value?: string;
  unit?: string;
  status?: string;
  detail?: string;
}

export interface BiomarkerReport {
  meta?: { definition?: string; tolerance?: number; generated_at?: string; notes?: string[] };
  biomarkers: BiomarkerEntry[];
}

export interface CohortVariant {
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  seen_runs: number;
  frequency: number;
  genes?: string[];
  consequences?: string[];
  clinvar_significance?: string[];
}

export interface CohortTable {
  meta?: { name?: string; total_runs?: number; generated_at?: string };
  variants: CohortVariant[];
  genes?: { gene: string; variant_count: number; runs_with_gene: number }[];
}

export interface ResearchData {
  manifest: ResearchManifest;
  variants: VariantTable | null;
  readiness: ReadinessTable | null;
  reportMeta: ReportMeta | null;
  family: FamilyTable | null;
  biomarkers: BiomarkerReport | null;
  cohort: CohortTable | null;
  reportHtml: string | null;
}

/** Directory holding the research manifest and artifacts. */
export function researchDir(): string {
  return process.env.CONTIG_RESEARCH_DIR
    ? path.resolve(process.env.CONTIG_RESEARCH_DIR)
    : path.resolve(process.cwd(), "research");
}

function repoRoot(): string {
  return path.resolve(process.cwd(), "..");
}

function resolveArtifact(value?: string): string | null {
  if (!value) return null;
  return path.isAbsolute(value) ? value : path.resolve(repoRoot(), value);
}

async function readJson<T>(file: string | null): Promise<T | null> {
  if (!file) return null;
  try {
    return JSON.parse(await fs.readFile(file, "utf8")) as T;
  } catch {
    return null;
  }
}

export async function loadResearch(): Promise<ResearchData | null> {
  const manifestFile = path.join(researchDir(), "manifest.json");
  const manifest = await readJson<ResearchManifest>(manifestFile);
  if (!manifest) return null;

  const variants = await readJson<VariantTable>(resolveArtifact(manifest.variants));
  const readiness = await readJson<ReadinessTable>(resolveArtifact(manifest.readiness));
  const reportMeta = await readJson<ReportMeta>(resolveArtifact(manifest.report_meta));
  const family = await readJson<FamilyTable>(resolveArtifact(manifest.family));
  const biomarkers = await readJson<BiomarkerReport>(resolveArtifact(manifest.biomarkers));
  const cohort = await readJson<CohortTable>(resolveArtifact(manifest.cohort));
  const reportHtmlPath = resolveArtifact(manifest.report_html);
  let reportHtml: string | null = null;
  if (reportHtmlPath) {
    try {
      reportHtml = await fs.readFile(reportHtmlPath, "utf8");
    } catch {
      reportHtml = null;
    }
  }

  return { manifest, variants, readiness, reportMeta, family, biomarkers, cohort, reportHtml };
}

/** Run the grounded ask command against the manifest's run context. */
export async function askResearch(question: string): Promise<unknown> {
  const manifest = await readJson<ResearchManifest>(path.join(researchDir(), "manifest.json"));
  if (!manifest?.run_id) throw new Error("research manifest has no run_id");
  if (!question.trim()) throw new Error("question is required");

  const args = ["ask", manifest.run_id, question, "--json"];
  const runsDir = resolveArtifact(manifest.runs_dir);
  const variants = resolveArtifact(manifest.variants);
  const readiness = resolveArtifact(manifest.readiness);
  if (runsDir) args.push("--runs-dir", runsDir);
  if (variants) args.push("--variants", variants);
  if (readiness) args.push("--readiness", readiness);

  const cli = process.env.CONTIG_CLI;
  const command = cli ? cli : "uv";
  const argv = cli ? args : ["run", "contig", ...args];
  try {
    const { stdout } = await pexec(command, argv, {
      cwd: repoRoot(),
      maxBuffer: 4 * 1024 * 1024,
    });
    return JSON.parse(stdout) as unknown;
  } catch (err) {
    const message = err as Error & { stderr?: string };
    throw new Error(message.stderr?.trim() || message.message);
  }
}
