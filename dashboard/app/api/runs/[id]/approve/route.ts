import { NextResponse } from "next/server";

import { decideApproval, InvalidRunIdError, RunControlError } from "@/lib/runs";

// POST /api/runs/[id]/approve {decision: "approve" | "reject"}: resolve the patch
// a paused (awaiting_approval) run is waiting on. The dashboard never controls the
// engine directly; this shells out to `contig approve <id>` (with --reject for a
// rejection) via CONTIG_DISPATCH_CMD, which validates the run id and writes
// runs/<id>/approval.json so the engine's poll unblocks. A bad id or decision is
// 400; a CLI failure is 409.
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  let decision: unknown;
  try {
    decision = ((await req.json()) as { decision?: unknown })?.decision;
  } catch {
    return NextResponse.json({ error: "A JSON body is required." }, { status: 400 });
  }
  if (decision !== "approve" && decision !== "reject") {
    return NextResponse.json(
      { error: 'decision must be "approve" or "reject".' },
      { status: 400 },
    );
  }

  try {
    await decideApproval(id, decision);
    return NextResponse.json({ ok: true, decision }, { status: 202 });
  } catch (err) {
    if (err instanceof InvalidRunIdError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    if (err instanceof RunControlError) {
      return NextResponse.json({ error: err.message }, { status: 409 });
    }
    return NextResponse.json(
      { error: "Could not record the decision." },
      { status: 500 },
    );
  }
}
