import { NextResponse } from "next/server";

import { requireWriter } from "@/lib/auth0";
import { cancelRun, InvalidRunIdError, RunControlError } from "@/lib/runs";

// POST /api/runs/[id]/cancel: stop an active run. The dashboard never controls a
// process directly; this shells out to `contig cancel <id>` (CONTIG_DISPATCH_CMD),
// which validates the run id, sends SIGTERM to the run's process group, and writes
// status.json state "cancelled". A bad id is 400; a run that cannot be cancelled
// (not active) is 409.
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const denied = await requireWriter();
  if (denied) return denied;
  const { id } = await params;
  try {
    await cancelRun(id);
    return NextResponse.json({ ok: true }, { status: 202 });
  } catch (err) {
    if (err instanceof InvalidRunIdError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    if (err instanceof RunControlError) {
      return NextResponse.json({ error: err.message }, { status: 409 });
    }
    return NextResponse.json(
      { error: "Could not cancel the run." },
      { status: 500 },
    );
  }
}
