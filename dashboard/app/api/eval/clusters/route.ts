import { NextResponse } from "next/server";

import { getClusters } from "@/lib/runs";

// GET /api/eval/clusters: the recurring failure modes (PRD contract B), grouped by
// failure class plus a normalized log signature and ordered worst first. The
// clustering lives in the engine; this shells out to `contig clusters --json`. A
// read-only route over the corpus (no run id, no per-user data), so it is not gated
// by the writer role and needs no ownership scope. An unavailable or unparseable
// CLI is 502, so the clusters view can degrade gracefully.
export const dynamic = "force-dynamic";

export async function GET() {
  const clusters = await getClusters();
  if (!clusters) {
    return NextResponse.json(
      { error: "Could not load the failure clusters." },
      { status: 502 },
    );
  }
  return NextResponse.json(clusters, { status: 200 });
}
