import { NextResponse } from "next/server";

import { getEstimate, EstimateValidationError } from "@/lib/runs";

// POST /api/runs/estimate: a pre-run runtime and cost estimate for a pipeline and
// sample sheet (PRD contract B), shelling out to `contig estimate --json`. The
// estimate model lives in the engine; this route validates the pipeline (known
// set) and the sheet (a real path), then returns the parsed EstimateReport. A
// read-only route: any authenticated user may see an estimate, so it is not gated
// by the writer role (the proxy still requires a session when auth is live). A bad
// pipeline or missing sheet is 400; an unavailable or unparseable CLI is 502.
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const str = (v: unknown) => (typeof v === "string" ? v : undefined);
  try {
    const report = await getEstimate({
      pipeline: str(body.pipeline) ?? "",
      input: str(body.input) ?? "",
      rateCpuHour: str(body.rateCpuHour),
      rateMemGbHour: str(body.rateMemGbHour),
      currency: str(body.currency),
    });
    if (!report) {
      return NextResponse.json(
        { error: "Could not produce an estimate." },
        { status: 502 },
      );
    }
    return NextResponse.json(report, { status: 200 });
  } catch (err) {
    if (err instanceof EstimateValidationError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    return NextResponse.json(
      { error: "Could not produce an estimate." },
      { status: 500 },
    );
  }
}
