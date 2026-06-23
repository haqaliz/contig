import { currentViewer } from "@/lib/auth0";
import { getRun, getRunReportHtml, InvalidRunIdError } from "@/lib/runs";

// GET /api/runs/[id]/report: the self-contained shareable HTML report for a run
// (PRD contract D), shelling out to `contig show <id> --html`. The report is
// rendered offline by the engine (no scripts, no network, fully escaped, and
// print-to-PDF friendly); this route serves the bytes for download with a
// filename. A read-only route: any authenticated viewer may download a report for
// a run they can see, so it is not gated by the writer role, but it IS scoped by
// per-user isolation (a run the viewer may not see reads as absent, so 404). The
// run id is validated in the data layer and passed as a positional after "--".
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    // Enforce isolation: a run this viewer may not see is 404, never served.
    const viewer = await currentViewer();
    const record = await getRun(id, viewer);
    if (!record) {
      return Response.json({ error: "Run not found." }, { status: 404 });
    }
    const html = await getRunReportHtml(id);
    if (!html) {
      return Response.json(
        { error: "Could not render the report." },
        { status: 502 },
      );
    }
    return new Response(html, {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Disposition": `attachment; filename="${id}.report.html"`,
      },
    });
  } catch (err) {
    if (err instanceof InvalidRunIdError) {
      return Response.json({ error: err.message }, { status: 400 });
    }
    return Response.json(
      { error: "Could not render the report." },
      { status: 500 },
    );
  }
}
