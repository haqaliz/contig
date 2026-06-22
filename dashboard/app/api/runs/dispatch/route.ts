import { NextResponse } from "next/server";

import { requireWriter } from "@/lib/auth0";
import { dispatchTestProfileRun, DispatchBusyError } from "@/lib/runs";

// POST /api/runs/dispatch: launch a test-profile run (no inputs). One at a time.
// This is the v1a dispatch plumbing: it spawns the existing CLI detached and
// returns the run id; the run becomes observable via its status.json marker.
// A write action: requires the writer/admin role (the dev bypass allows it).
export async function POST() {
  const denied = await requireWriter();
  if (denied) return denied;
  try {
    const { run_id } = await dispatchTestProfileRun();
    return NextResponse.json({ run_id }, { status: 202 });
  } catch (err) {
    if (err instanceof DispatchBusyError) {
      return NextResponse.json({ error: err.message }, { status: 409 });
    }
    return NextResponse.json({ error: "Could not start the run." }, { status: 500 });
  }
}
