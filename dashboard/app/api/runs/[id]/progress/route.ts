import { NextResponse } from "next/server";

import { getRunLogTail, getRunProgress } from "@/lib/runs";

// GET /api/runs/[id]/progress: a live snapshot for the running view to poll.
// Returns the progress summary (state, elapsed, tasks, repairs) plus the log
// tail, both derived server-side from the run dir. Never cached: a running run
// changes on disk every second.
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const [progress, logTail] = await Promise.all([
    getRunProgress(id),
    getRunLogTail(id),
  ]);
  return NextResponse.json({ progress, logTail });
}
