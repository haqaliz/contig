// Read-only access to the research-workbench JSON artifacts. The dashboard reads
// a small manifest from CONTIG_RESEARCH_DIR (default dashboard/research) and
// renders whatever tables are attached; it never writes or launches anything.
import "server-only";

import { promises as fs } from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";

import { runsDir } from "./runs";

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
  manifestSource: string;
  manifestPath: string;
}

/** Directory holding the explicit research manifest and artifacts. */
export function researchDir(): string {
  return process.env.CONTIG_RESEARCH_DIR
    ? path.resolve(process.env.CONTIG_RESEARCH_DIR)
    : path.resolve(process.cwd(), "research");
}

function repoRoot(): string {
  return path.resolve(process.cwd(), "..");
}

interface ManifestLocation {
  file: string;
  baseDir: string;
  source: string;
}

async function exists(candidate: string): Promise<boolean> {
  try {
    await fs.access(candidate);
    return true;
  } catch {
    return false;
  }
}

/**
 * The explicit manifest wins. Otherwise use the newest
 * runs/<run_id>/research/manifest.json (read-only, no writes).
 */
async function manifestLocation(): Promise<ManifestLocation | null> {
  const explicitDir = researchDir();
  const explicit = path.join(explicitDir, "manifest.json");
  if (await exists(explicit)) {
    return { file: explicit, baseDir: explicitDir, source: "explicit manifest" };
  }

  const runs = runsDir();
  let entries: string[];
  try {
    entries = await fs.readdir(runs);
  } catch {
    return null;
  }
  const candidates: (ManifestLocation & { mtime: number })[] = [];
  for (const name of entries) {
    const file = path.join(runs, name, "research", "manifest.json");
    try {
      const stat = await fs.stat(file);
      if (stat.isFile()) {
        candidates.push({
          file,
          baseDir: path.dirname(file),
          source: `runs/${name}/research`,
          mtime: stat.mtimeMs,
        });
      }
    } catch {
      // a run without research artifacts is normal
    }
  }
  candidates.sort((a, b) => b.mtime - a.mtime);
  return candidates[0] ?? null;
}

/**
 * Resolve a manifest path. Per-run manifests resolve against their own
 * directory first; the repo-root fallback keeps existing explicit manifests
 * working. A missing file is returned as the local candidate so the error
 * points at the intended location.
 */
async function resolveArtifact(
  value: string | undefined,
  baseDir: string,
): Promise<string | null> {
  if (!value) return null;
  if (path.isAbsolute(value)) return value;
  const local = path.resolve(baseDir, value);
  if (await exists(local)) return local;
  const repo = path.resolve(repoRoot(), value);
  if (await exists(repo)) return repo;
  return local;
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
  const location = await manifestLocation();
  if (!location) return null;
  const manifest = await readJson<ResearchManifest>(location.file);
  if (!manifest) return null;

  const variants = await readJson<VariantTable>(
    await resolveArtifact(manifest.variants, location.baseDir),
  );
  const readiness = await readJson<ReadinessTable>(
    await resolveArtifact(manifest.readiness, location.baseDir),
  );
  const reportMeta = await readJson<ReportMeta>(
    await resolveArtifact(manifest.report_meta, location.baseDir),
  );
  const family = await readJson<FamilyTable>(
    await resolveArtifact(manifest.family, location.baseDir),
  );
  const biomarkers = await readJson<BiomarkerReport>(
    await resolveArtifact(manifest.biomarkers, location.baseDir),
  );
  const cohort = await readJson<CohortTable>(
    await resolveArtifact(manifest.cohort, location.baseDir),
  );
  const reportHtmlPath = await resolveArtifact(
    manifest.report_html,
    location.baseDir,
  );
  let reportHtml: string | null = null;
  if (reportHtmlPath) {
    try {
      reportHtml = await fs.readFile(reportHtmlPath, "utf8");
    } catch {
      reportHtml = null;
    }
  }

  return {
    manifest,
    variants,
    readiness,
    reportMeta,
    family,
    biomarkers,
    cohort,
    reportHtml,
    manifestSource: location.source,
    manifestPath: location.file,
  };
}

/** Run the grounded ask command against the manifest's run context. */
export async function askResearch(question: string): Promise<unknown> {
  const location = await manifestLocation();
  if (!location) throw new Error("research manifest not found");
  const manifest = await readJson<ResearchManifest>(location.file);
  if (!manifest?.run_id) throw new Error("research manifest has no run_id");
  if (!question.trim()) throw new Error("question is required");

  const args = ["ask", manifest.run_id, question, "--json"];
  const runsDirArg = await resolveArtifact(manifest.runs_dir, location.baseDir);
  const variants = await resolveArtifact(manifest.variants, location.baseDir);
  const readiness = await resolveArtifact(manifest.readiness, location.baseDir);
  if (runsDirArg) args.push("--runs-dir", runsDirArg);
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
