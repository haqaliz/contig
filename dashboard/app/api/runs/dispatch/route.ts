import { NextResponse } from "next/server";

import { currentViewer, requireWriter } from "@/lib/auth0";
import {
  dispatchTestProfileRun,
  DispatchBusyError,
  writeRunOwner,
} from "@/lib/runs";

// POST /api/runs/dispatch: launch a test-profile run (no inputs). One at a time.
// This is the v1a dispatch plumbing: it spawns the existing CLI detached and
// returns the run id; the run becomes observable via its status.json marker.
// A write action: requires the writer/admin role (the dev bypass allows it).
export async function POST() {
  const denied = await requireWriter();
  if (denied) return denied;
  try {
    const viewer = await currentViewer();
    const { run_id } = await dispatchTestProfileRun();
    // Tag the run with its owner so per-user isolation (PRD contract E) can scope
    // it later. Best effort: a failed write leaves the run admin-only, not broken.
    await writeRunOwner(run_id, { owner: viewer.owner, email: viewer.email });
    return NextResponse.json({ run_id }, { status: 202 });
  } catch (err) {
    if (err instanceof DispatchBusyError) {
      return NextResponse.json({ error: err.message }, { status: 409 });
    }
    return NextResponse.json({ error: "Could not start the run." }, { status: 500 });
  }
}
