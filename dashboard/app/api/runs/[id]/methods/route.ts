import { currentViewer } from "@/lib/auth0";
import { getRun, getRunMethods, InvalidRunIdError } from "@/lib/runs";

// GET /api/runs/[id]/methods: a deterministic, citation-ready methods paragraph
// for a run (PRD contract C), shelling out to `contig methods <id>`. The generator
// is offline and templated (no LLM, no network) and lives in the engine; this
// route serves the text for download. A read-only route scoped by per-user
// isolation: a run the viewer may not see reads as absent (404). The run id is
// validated in the data layer and passed as a positional after "--".
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const viewer = await currentViewer();
    const record = await getRun(id, viewer);
    if (!record) {
      return Response.json({ error: "Run not found." }, { status: 404 });
    }
    const methods = await getRunMethods(id);
    if (!methods) {
      return Response.json(
        { error: "Could not generate the methods text." },
        { status: 502 },
      );
    }
    return new Response(methods, {
      status: 200,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": `attachment; filename="${id}.methods.txt"`,
      },
    });
  } catch (err) {
    if (err instanceof InvalidRunIdError) {
      return Response.json({ error: err.message }, { status: 400 });
    }
    return Response.json(
      { error: "Could not generate the methods text." },
      { status: 500 },
    );
  }
}
