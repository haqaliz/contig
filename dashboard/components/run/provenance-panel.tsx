// Pinned provenance: everything needed to reproduce and audit the run. Hashes are
// shown monospace and truncated, with the full value on hover (title attribute) so
// the panel stays scannable without losing the exact digest. Reproducibility is a
// core requirement, not a nice-to-have, so this surfaces the pins the engine
// recorded: tool versions, execution target, parameters, and input/output/container
// checksums.
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ExecutionTarget, RunRecord } from "@/lib/types";

// A hash/digest cell: monospace, middle-truncated visually, full value on hover.
function Hash({ value }: { value: string }) {
  return (
    <span
      title={value}
      className="block max-w-[28ch] truncate font-mono text-xs"
    >
      {value}
    </span>
  );
}

function stringify(value: unknown): string {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// A key/value table that renders nothing-but-a-note when the map is empty.
function KvTable({
  entries,
  empty,
  mono = false,
  keyLabel = "Key",
  valueLabel = "Value",
}: {
  entries: [string, unknown][];
  empty: string;
  mono?: boolean;
  keyLabel?: string;
  valueLabel?: string;
}) {
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">{keyLabel}</TableHead>
          <TableHead scope="col">{valueLabel}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map(([k, v]) => (
          <TableRow key={k}>
            <TableHead scope="row" className="font-mono text-xs font-normal whitespace-normal">
              {k}
            </TableHead>
            <TableCell className="whitespace-normal">
              {mono ? (
                <Hash value={stringify(v)} />
              ) : (
                <span className="font-mono text-xs">{stringify(v)}</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function TargetSummary({ target }: { target: ExecutionTarget }) {
  const rows: [string, string][] = [
    ["Backend", target.backend],
    ["Container runtime", target.container_runtime],
    ["Engine", target.engine ?? "n/a"],
    ["Work dir", target.work_dir],
  ];
  const limits = Object.entries(target.resource_limits ?? {});
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        {rows.map(([label, val]) => (
          <div key={label}>
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="font-mono text-xs break-words">{val}</dd>
          </div>
        ))}
      </dl>
      <div>
        <h4 className="mb-1 text-xs font-medium text-muted-foreground">
          Resource limits
        </h4>
        <KvTable
          entries={limits}
          empty="No explicit resource limits (engine defaults)."
          keyLabel="Resource"
          valueLabel="Limit"
        />
      </div>
    </div>
  );
}

export function ProvenancePanel({ record }: { record: RunRecord }) {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Provenance</CardTitle>
          <CardDescription>
            Pinned versions and the execution target, so this run can be
            reproduced and audited.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">Pipeline</dt>
              <dd className="font-mono text-xs break-words">{record.pipeline}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Revision</dt>
              <dd className="font-mono text-xs break-words">
                {record.pipeline_revision}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">contig version</dt>
              <dd className="font-mono text-xs break-words">
                {record.contig_version ?? "n/a"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">nextflow version</dt>
              <dd className="font-mono text-xs break-words">
                {record.nextflow_version ?? "n/a"}
              </dd>
            </div>
          </dl>
          <div>
            <h3 className="mb-2 text-sm font-medium">Execution target</h3>
            <TargetSummary target={record.target} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Parameters</CardTitle>
        </CardHeader>
        <CardContent>
          <KvTable
            entries={Object.entries(record.parameters)}
            empty="No parameters recorded."
            keyLabel="Parameter"
            valueLabel="Value"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Checksums and digests</CardTitle>
          <CardDescription>
            Hover any value to see the full hash.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div>
            <h3 className="mb-2 text-sm font-medium">Input checksums</h3>
            <KvTable
              entries={Object.entries(record.input_checksums)}
              empty="No input checksums recorded."
              mono
              keyLabel="Input"
              valueLabel="Checksum"
            />
          </div>
          <div>
            <h3 className="mb-2 text-sm font-medium">Output checksums</h3>
            <KvTable
              entries={Object.entries(record.output_checksums)}
              empty="No output checksums recorded."
              mono
              keyLabel="Output"
              valueLabel="Checksum"
            />
          </div>
          <div>
            <h3 className="mb-2 text-sm font-medium">Container digests</h3>
            <KvTable
              entries={Object.entries(record.container_digests)}
              empty="No container digests recorded."
              mono
              keyLabel="Container"
              valueLabel="Digest"
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
