import { NextResponse } from "next/server";

import { getLaunchManifest } from "@/lib/runs";

// GET /api/runs/[id]/manifest: the launch manifest a run wrote (launch.json),
// so the "Edit and relaunch" form can pre-fill its fields from a prior run.
// Returns 404 if the run has no manifest (an older run, or one that never
// reached the manifest write).
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const manifest = await getLaunchManifest(id);
  if (!manifest) {
    return NextResponse.json(
      { error: "No launch manifest for this run." },
      { status: 404 },
    );
  }
  return NextResponse.json({ manifest });
}
