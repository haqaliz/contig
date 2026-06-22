import { NextResponse } from "next/server";

import { getRunCost, InvalidRunIdError } from "@/lib/runs";

// GET /api/runs/[id]/cost?cpuHour=&memGbHour=&currency=: the cost report for a
// run at the given rates (all optional, default 0 = free local compute). The
// cost model lives in the engine; this shells out to `contig cost <id> --json`.
// A read-only route: any authenticated user may see a cost estimate, so it is
// not gated by the writer role (the proxy still requires a session when auth is
// live). A bad id is 400; an unavailable or unparseable CLI is 502.
export const dynamic = "force-dynamic";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const url = new URL(req.url);
  const cpuHour = url.searchParams.get("cpuHour") ?? undefined;
  const memGbHour = url.searchParams.get("memGbHour") ?? undefined;
  const currency = url.searchParams.get("currency") ?? undefined;
  try {
    const report = await getRunCost(id, { cpuHour, memGbHour, currency });
    if (!report) {
      return NextResponse.json(
        { error: "Could not compute the cost." },
        { status: 502 },
      );
    }
    return NextResponse.json(report, { status: 200 });
  } catch (err) {
    if (err instanceof InvalidRunIdError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    return NextResponse.json(
      { error: "Could not compute the cost." },
      { status: 500 },
    );
  }
}
