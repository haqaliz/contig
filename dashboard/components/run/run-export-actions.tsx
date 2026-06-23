// Provenance download buttons on the run detail page (PRD contract C). A run can
// be exported as an RO-Crate metadata JSON (machine-readable provenance) and as a
// deterministic, citation-ready methods paragraph. Both are produced offline by
// the engine (`contig export --rocrate`, `contig methods`) and served by read-only
// API routes; these are plain download links, so this stays a Server Component
// with no client island. The links are real anchors (role link), so we style them
// with buttonVariants directly rather than a button, keeping the correct element.
import { FileJson, FileText } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";

export function RunExportActions({ id }: { id: string }) {
  const base = `/api/runs/${encodeURIComponent(id)}`;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Export and cite</CardTitle>
        <CardDescription>
          Download this run&apos;s provenance as an RO-Crate (machine readable) or
          a citation-ready methods paragraph. Both are generated offline from the
          recorded bundle, with no network and no model in the loop.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-center gap-2">
          {/* download attribute so the browser saves the file rather than
              navigating to it; the route also sets a Content-Disposition. */}
          <a
            href={`${base}/export`}
            download
            className={buttonVariants({ variant: "outline", size: "sm", className: "gap-2" })}
          >
            <FileJson className="size-4" aria-hidden="true" />
            Download RO-Crate
          </a>
          <a
            href={`${base}/methods`}
            download
            className={buttonVariants({ variant: "outline", size: "sm", className: "gap-2" })}
          >
            <FileText className="size-4" aria-hidden="true" />
            Download methods
          </a>
        </div>
      </CardContent>
    </Card>
  );
}
