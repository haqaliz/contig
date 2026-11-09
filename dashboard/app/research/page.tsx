// Read-only research dashboard. It renders the JSON artifacts produced by the
// variants/readiness/report/family/biomarkers/cohort commands from a local
// manifest; it never writes or launches anything. The only interactive piece is
// the grounded ask panel, which calls a read-only API route.
import { PageHeader } from "@/components/page-header";
import { AskPanel } from "@/components/research/ask-panel";
import { loadResearch } from "@/lib/research";

export const dynamic = "force-dynamic";

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  return String(value);
}

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : `${(value * 100).toFixed(1)}%`;
}

function readinessClass(value?: string): string {
  if (value === "ready") return "bg-emerald-100 text-emerald-800";
  if (value === "caution") return "bg-amber-100 text-amber-800";
  if (value === "not-interpretable") return "bg-red-100 text-red-800";
  return "bg-muted text-muted-foreground";
}

function Badge({ value }: { value?: string }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${readinessClass(value)}`}>
      {value ?? "unknown"}
    </span>
  );
}

function DataTable({
  headers,
  rows,
  empty = "No rows.",
}: {
  headers: string[];
  rows: React.ReactNode[][];
  empty?: string;
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-left text-xs">
        <thead className="bg-muted/60 text-muted-foreground">
          <tr>
            {headers.map((header) => (
              <th key={header} className="px-3 py-2 font-medium whitespace-nowrap">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-3 py-2 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Section({
  title,
  count,
  description,
  children,
}: {
  title: string;
  count?: number;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3 rounded-xl border bg-card p-5">
      <div>
        <h2 className="font-heading text-base font-medium">
          {title}
          {count !== undefined ? (
            <span className="ml-1.5 font-normal text-muted-foreground tabular-nums">({count})</span>
          ) : null}
        </h2>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

export default async function ResearchPage() {
  const data = await loadResearch();

  if (!data) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Research"
          description="Read-only variants, readiness, reports, family, biomarker, and cohort artifacts."
        />
        <div className="rounded-xl border border-dashed p-10 text-center">
          <h2 className="text-base font-medium">No research manifest yet</h2>
          <p className="mx-auto mt-2 max-w-prose text-sm text-muted-foreground">
            Create <code className="font-mono">dashboard/research/manifest.json</code> (copy
            <code className="mx-1 font-mono">manifest.example.json</code>) pointing at the JSON
            files produced by the CLI. The dashboard only reads those files; it never writes or
            launches a run.
          </p>
          <p className="mx-auto mt-3 max-w-prose text-sm text-muted-foreground">
            Example: <code className="font-mono">contig variants … --json --out research/variants.json</code>,
            then set <code className="font-mono">&quot;variants&quot;: &quot;research/variants.json&quot;</code>.
          </p>
        </div>
      </div>
    );
  }

  const variants = data.variants?.variants ?? [];
  const targets = data.readiness?.targets ?? [];
  const genes = data.readiness?.genes ?? [];
  const report = data.reportMeta;
  const family = data.family?.rows ?? [];
  const biomarkers = data.biomarkers?.biomarkers ?? [];
  const cohort = data.cohort?.variants ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Research"
        count={variants.length || undefined}
        description="Read-only evidence, readiness, reports, family, biomarkers, and cohort context. Research use only; no clinical claims."
      />
      {data.manifestSource.startsWith("runs/") ? (
        <p className="text-xs text-muted-foreground">
          Auto-discovered from <code className="font-mono">{data.manifestSource}</code>.
        </p>
      ) : null}

      <Section
        title="Variant evidence"
        count={variants.length}
        description={data.variants?.meta?.generated_at ? `Generated ${data.variants.meta.generated_at}` : undefined}
      >
        <DataTable
          headers={["Gene", "Variant", "rsID", "GT", "Depth", "VAF", "Consequence", "ClinVar", "ClinVar review", "Population AF", "Iranome AF"]}
          rows={variants.slice(0, 100).map((row) => {
            const key = row.key ?? {};
            return [
              fmt(row.gene),
              `${fmt(key.chrom)}:${fmt(key.pos)} ${fmt(key.ref)}>${fmt(key.alt)}`,
              fmt(row.rsid),
              fmt(row.genotype),
              fmt(row.depth),
              fmt(row.vaf),
              fmt(row.consequence),
              fmt(row.clinvar_significance),
              fmt(row.clinvar_review_status),
              fmt(row.population_af ?? row.gnomad_af),
              fmt(row.iranome_af),
            ];
          })}
          empty="No variant table attached."
        />
        {variants.length > 100 ? (
          <p className="text-xs text-muted-foreground">Showing 100 of {variants.length} rows.</p>
        ) : null}
      </Section>

      <Section
        title="Coverage readiness"
        count={genes.length || targets.length}
        description="Gene-level summary is shown first when available; target rows are the underlying exons/intervals."
      >
        {genes.length > 0 ? (
          <>
            <h3 className="text-sm font-medium">By gene</h3>
            <DataTable
              headers={["Gene", "Targets", "Mean depth", "% ≥20x", "Zero bases", "Readiness", "Reason"]}
              rows={genes.map((gene) => [
                gene.gene,
                gene.targets,
                fmt(gene.mean_depth),
                pct(gene.pct_20x),
                gene.zero_bases,
                <Badge key="state" value={gene.readiness} />,
                gene.reason,
              ])}
            />
          </>
        ) : null}
        <h3 className="text-sm font-medium">Targets</h3>
        <DataTable
          headers={["Target", "Gene", "Mean depth", "% ≥20x", "% ≥50x", "% ≥100x", "Zero bases", "Caveats", "Readiness", "Reason"]}
          rows={targets.slice(0, 100).map((row) => [
            fmt(row.target?.name),
            fmt(row.target?.gene),
            fmt(row.mean_depth),
            pct(row.pct_20x),
            pct(row.pct_50x),
            pct(row.pct_100x),
            fmt(row.zero_bases),
            (row.caveats ?? []).join("; "),
            <Badge key="state" value={row.readiness} />,
            fmt(row.reason),
          ])}
          empty="No readiness table attached."
        />
      </Section>

      <Section
        title="Research report"
        description={report?.spec?.title ?? "No report sidecar attached."}
      >
        {report ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <a
                className="rounded-md border px-3 py-1.5 font-medium hover:bg-muted"
                href="/api/research/report"
                target="_blank"
                rel="noreferrer"
              >
                Open report HTML
              </a>
              <span className="text-muted-foreground">
                Template: {fmt(report.spec?.template)} · Generated {fmt(report.generated_at)}
              </span>
            </div>
            <DataTable
              headers={["Kind", "Path", "SHA-256"]}
              rows={(report.inputs ?? []).map((input) => [input.kind, input.path, input.sha256])}
            />
            <p className="text-xs text-muted-foreground">
              The HTML hash is <code className="font-mono">{fmt(report.html_sha256)}</code>. Verify
              inputs and the HTML with <code className="font-mono">contig report-check</code>.
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No report sidecar attached.</p>
        )}
      </Section>

      <Section title="Ask the run" description="Grounded answers with source citations; no clinical interpretation.">
        <AskPanel />
      </Section>

      <Section title="Family / trio" count={family.length} description="Inheritance, Mendelian consistency, and de novo candidates.">
        <DataTable
          headers={["Child", "Variant", "Gene", "Child GT", "Father GT", "Mother GT", "Inheritance", "Consistent", "De novo"]}
          rows={family.slice(0, 100).map((row) => {
            const key = row.key ?? {};
            return [
              fmt(row.child),
              `${fmt(key.chrom)}:${fmt(key.pos)} ${fmt(key.ref)}>${fmt(key.alt)}`,
              fmt(row.gene),
              fmt(row.child_gt),
              fmt(row.father_gt),
              fmt(row.mother_gt),
              fmt(row.inheritance),
              row.mendelian_consistent === null || row.mendelian_consistent === undefined
                ? "not evaluated"
                : row.mendelian_consistent
                  ? "yes"
                  : "no",
              row.de_novo_candidate ? "yes" : "no",
            ];
          })}
          empty="No family table attached."
        />
      </Section>

      <Section title="Biomarkers" count={biomarkers.length} description="TMB, MSI, LOH, and CNV verification state.">
        <DataTable
          headers={["Biomarker", "Value", "Unit", "Status", "Detail"]}
          rows={biomarkers.map((entry) => [
            entry.name,
            fmt(entry.value),
            fmt(entry.unit),
            <Badge key="state" value={entry.status} />,
            fmt(entry.detail),
          ])}
          empty="No biomarker report attached."
        />
      </Section>

      <Section title="Cohort frequency" count={cohort.length} description="Local-only cohort context; no data leaves this machine.">
        <DataTable
          headers={["Variant", "Genes", "Seen runs", "Frequency", "Consequence", "ClinVar"]}
          rows={cohort.slice(0, 100).map((row) => [
            `${row.chrom}:${row.pos} ${row.ref}>${row.alt}`,
            (row.genes ?? []).join(", "),
            row.seen_runs,
            pct(row.frequency),
            (row.consequences ?? []).join(", "),
            (row.clinvar_significance ?? []).join(", "),
          ])}
          empty="No cohort table attached."
        />
      </Section>
    </div>
  );
}
