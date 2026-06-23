import { NextResponse } from "next/server";

import { requireWriter } from "@/lib/auth0";
import { decideApproval, InvalidRunIdError, RunControlError } from "@/lib/runs";

// POST /api/runs/[id]/approve {decision: "approve" | "reject", choice?: number}:
// resolve the decision a paused (awaiting_approval) run is waiting on. The
// dashboard never controls the engine directly; this shells out to `contig approve
// <id>` (with --reject for a rejection, or --choose=<n> to pick a ranked option for
// a guided-escalation choice, PRD contract D) via CONTIG_DISPATCH_CMD, which
// validates the run id and writes runs/<id>/approval.json so the engine's poll
// unblocks. The choice index is validated as a non-negative integer here; the
// engine validates it against the actual options length and rejects an out-of-range
// index. A bad id, decision, or choice is 400; a CLI failure is 409.
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const denied = await requireWriter();
  if (denied) return denied;
  const { id } = await params;

  let body: { decision?: unknown; choice?: unknown };
  try {
    body = (await req.json()) as { decision?: unknown; choice?: unknown };
  } catch {
    return NextResponse.json({ error: "A JSON body is required." }, { status: 400 });
  }
  const decision = body?.decision;
  if (decision !== "approve" && decision !== "reject") {
    return NextResponse.json(
      { error: 'decision must be "approve" or "reject".' },
      { status: 400 },
    );
  }

  // The choice index is meaningful only on an approve (a guided-escalation choice).
  // When present it must be a non-negative integer; a reject ignores it. The engine
  // bounds-checks it against the options length, so an out-of-range index is
  // rejected there, never silently applied.
  let choice: number | undefined;
  if (decision === "approve" && body?.choice !== undefined && body?.choice !== null) {
    if (typeof body.choice !== "number" || !Number.isInteger(body.choice) || body.choice < 0) {
      return NextResponse.json(
        { error: "choice must be a non-negative integer." },
        { status: 400 },
      );
    }
    choice = body.choice;
  }

  try {
    await decideApproval(id, decision, choice);
    return NextResponse.json({ ok: true, decision, choice }, { status: 202 });
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
