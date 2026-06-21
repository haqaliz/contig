import { NextResponse } from "next/server";

import { planRun } from "@/lib/runs";

// POST /api/runs/plan { goal, input, genome? | (fasta?, gtf?) }: produce an
// approvable plan (pipeline + params + warnings) for the launch form. Input
// validation (paths exist, safe keys) happens in planRun; bad input returns an
// error string for the form to show.
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const str = (v: unknown) => (typeof v === "string" ? v : undefined);
  const { plan, error } = await planRun({
    goal: str(body.goal) ?? "",
    input: str(body.input) ?? "",
    genome: str(body.genome),
    fasta: str(body.fasta),
    gtf: str(body.gtf),
  });
  if (error) return NextResponse.json({ error }, { status: 400 });
  return NextResponse.json({ plan });
}
