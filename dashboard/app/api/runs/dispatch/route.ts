import { NextResponse } from "next/server";

import { dispatchTestProfileRun, DispatchBusyError } from "@/lib/runs";

// POST /api/runs/dispatch: launch a test-profile run (no inputs). One at a time.
// This is the v1a dispatch plumbing: it spawns the existing CLI detached and
// returns the run id; the run becomes observable via its status.json marker.
export async function POST() {
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
