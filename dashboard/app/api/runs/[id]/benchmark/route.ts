import { NextResponse } from "next/server";

import { currentViewer } from "@/lib/auth0";
import { getBenchmark, getRun, InvalidRunIdError } from "@/lib/runs";

// GET /api/runs/[id]/benchmark?tolerance=: the cross-run benchmark for a run (PRD
// contract A). The comparison model lives in the engine; this shells out to
// `contig benchmark <id> --json`, which compares the run against the designated
// reference for its (pipeline, assay) by QC metric values within a relative
// tolerance plus structural shape. A read-only route: any authenticated user may
// see a benchmark, so it is not gated by the writer role, but it IS ownership
// scoped (PRD contract E): a run the viewer may not see reads as absent and 404s,
// so a benchmark never leaks another user's run. A bad id is 400; an unavailable
// or unparseable CLI is 502. A "no_reference" status is a normal 200 report.
export const dynamic = "force-dynamic";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  // Ownership scope first: resolve the run for the current viewer. A run they may
  // not see (or that does not exist) reads as absent, so we 404 before shelling
  // out, and the benchmark is never computed for a run outside their visibility.
  const viewer = await currentViewer();
  const record = await getRun(id, viewer);
  if (!record) {
    return NextResponse.json({ error: "Run not found." }, { status: 404 });
  }

  const url = new URL(req.url);
  // Validate tolerance up front: a non-negative decimal only. getBenchmark already
  // drops an unsafe value (it gates on the same shape and passes --tolerance=value
  // after a -- terminator, so a flag can never be smuggled), but reject it here with
  // a clear 400 rather than silently falling back to the default.
  const rawTolerance = url.searchParams.get("tolerance");
  if (rawTolerance !== null && !/^[0-9]+(\.[0-9]+)?$/.test(rawTolerance)) {
    return NextResponse.json({ error: "Invalid tolerance." }, { status: 400 });
  }
  const tolerance = rawTolerance ?? undefined;
  try {
    const report = await getBenchmark(id, tolerance);
    if (!report) {
      return NextResponse.json(
        { error: "Could not benchmark the run." },
        { status: 502 },
      );
    }
    return NextResponse.json(report, { status: 200 });
  } catch (err) {
    if (err instanceof InvalidRunIdError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    return NextResponse.json(
      { error: "Could not benchmark the run." },
      { status: 500 },
    );
  }
}
