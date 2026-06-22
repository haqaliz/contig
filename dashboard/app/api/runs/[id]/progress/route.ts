import { NextResponse } from "next/server";

import { getPendingApproval, getRunLogTail, getRunProgress } from "@/lib/runs";

// GET /api/runs/[id]/progress: a live snapshot for the running view to poll.
// Returns the progress summary (state, elapsed, tasks, repairs), the log tail,
// and the pending approval (when the run is paused on a gated patch), all derived
// server-side from the run dir. Never cached: a running run changes on disk every
// second.
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const [progress, logTail, pendingApproval] = await Promise.all([
    getRunProgress(id),
    getRunLogTail(id),
    getPendingApproval(id),
  ]);
  return NextResponse.json({ progress, logTail, pendingApproval });
}
