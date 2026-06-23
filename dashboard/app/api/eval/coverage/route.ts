import { NextResponse } from "next/server";

import { currentViewer } from "@/lib/auth0";
import { getCoverage } from "@/lib/runs";

// GET /api/eval/coverage: the corpus coverage report (PRD contract C): per-class
// support, the thin classes (fewer than 3 cases), the by-source breakdown, and a
// confirmed-over-time series. The coverage model lives in the engine; this shells
// out to `contig coverage --json`. A read-only route over the corpus (no run id, no
// per-user data), so it needs no ownership scope and no writer role, but it does
// require an authenticated viewer (the corpus is not public). Under the dev/test
// bypass the viewer is the local admin, so local use is unchanged. An unavailable or
// unparseable CLI is 502, so the panel can degrade.
export const dynamic = "force-dynamic";

export async function GET() {
  const viewer = await currentViewer();
  if (!viewer.owner) {
    return NextResponse.json({ error: "Unauthorized." }, { status: 401 });
  }
  const coverage = await getCoverage();
  if (!coverage) {
    return NextResponse.json(
      { error: "Could not load the coverage report." },
      { status: 502 },
    );
  }
  return NextResponse.json(coverage, { status: 200 });
}
