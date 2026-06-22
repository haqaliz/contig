import { NextResponse } from "next/server";

import { requireWriter } from "@/lib/auth0";
import { dispatchRealRun, DispatchBusyError, LaunchValidationError } from "@/lib/runs";

// POST /api/runs/launch: launch a real-data run from the approved plan + inputs.
// One at a time. All validation (paths exist, safe keys/caps, known pipeline) is
// in dispatchRealRun; user values are passed as --opt=value (no flag smuggling).
// A write action: requires the writer/admin role (the dev bypass allows it).
export async function POST(req: Request) {
  const denied = await requireWriter();
  if (denied) return denied;
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const str = (v: unknown) => (typeof v === "string" ? v : undefined);
  try {
    const { run_id } = await dispatchRealRun({
      input: str(body.input) ?? "",
      pipeline: str(body.pipeline),
      genome: str(body.genome),
      fasta: str(body.fasta),
      gtf: str(body.gtf),
      maxMemory: str(body.maxMemory),
      maxCpus: str(body.maxCpus),
    });
    return NextResponse.json({ run_id }, { status: 202 });
  } catch (err) {
    if (err instanceof DispatchBusyError) {
      return NextResponse.json({ error: err.message }, { status: 409 });
    }
    if (err instanceof LaunchValidationError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    return NextResponse.json({ error: "Could not start the run." }, { status: 500 });
  }
}
