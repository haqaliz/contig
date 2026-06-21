import { NextResponse } from "next/server";

import {
  dispatchReproduce,
  DispatchBusyError,
  LaunchValidationError,
  NoManifestError,
} from "@/lib/runs";

// POST /api/runs/[id]/reproduce: reproduce a run exactly from its launch.json.
// dispatchReproduce re-validates every input from the manifest (we never trust
// it blindly) and dispatches an identical run with a fresh server-generated id.
// One run at a time, matching the other dispatch routes.
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const { run_id } = await dispatchReproduce(id);
    return NextResponse.json({ run_id }, { status: 202 });
  } catch (err) {
    if (err instanceof NoManifestError) {
      return NextResponse.json({ error: err.message }, { status: 404 });
    }
    if (err instanceof DispatchBusyError) {
      return NextResponse.json({ error: err.message }, { status: 409 });
    }
    if (err instanceof LaunchValidationError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    return NextResponse.json(
      { error: "Could not reproduce the run." },
      { status: 500 },
    );
  }
}
