import { currentViewer } from "@/lib/auth0";
import { getRun, getRunRoCrate, InvalidRunIdError } from "@/lib/runs";

// GET /api/runs/[id]/export: the RO-Crate metadata JSON for a run (PRD contract
// C), shelling out to `contig export <id> --rocrate`. The provenance export lives
// in the engine (offline, no LLM, no network); this route serves the bytes for
// download with a filename. A read-only route: any authenticated user may export
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
    // Enforce isolation: a run this viewer may not see is 404, never exported.
    const viewer = await currentViewer();
    const record = await getRun(id, viewer);
    if (!record) {
      return Response.json({ error: "Run not found." }, { status: 404 });
    }
    const crate = await getRunRoCrate(id);
    if (!crate) {
      return Response.json(
        { error: "Could not export the run." },
        { status: 502 },
      );
    }
    return new Response(crate, {
      status: 200,
      headers: {
        "Content-Type": "application/ld+json; charset=utf-8",
        "Content-Disposition": `attachment; filename="${id}.ro-crate-metadata.json"`,
      },
    });
  } catch (err) {
    if (err instanceof InvalidRunIdError) {
      return Response.json({ error: err.message }, { status: 400 });
    }
    return Response.json(
      { error: "Could not export the run." },
      { status: 500 },
    );
  }
}
