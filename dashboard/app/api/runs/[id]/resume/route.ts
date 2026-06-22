import { NextResponse } from "next/server";

import { resumeRun, InvalidRunIdError, RunControlError } from "@/lib/runs";

// POST /api/runs/[id]/resume: re-run a cancelled or interrupted run with the SAME
// run id. The dashboard never spawns a process directly; this shells out to
// `contig resume <id>` (CONTIG_DISPATCH_CMD), which validates the run id and
// re-runs in the same run dir with Nextflow -resume so cached tasks are reused. A
// bad id is 400; a run that cannot be resumed is 409.
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    await resumeRun(id);
    return NextResponse.json({ run_id: id }, { status: 202 });
  } catch (err) {
    if (err instanceof InvalidRunIdError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    if (err instanceof RunControlError) {
      return NextResponse.json({ error: err.message }, { status: 409 });
    }
    return NextResponse.json(
      { error: "Could not resume the run." },
      { status: 500 },
    );
  }
}
