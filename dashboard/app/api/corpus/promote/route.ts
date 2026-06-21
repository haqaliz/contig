import { NextResponse } from "next/server";

import { FAILURE_CLASSES } from "@/lib/derive";
import { promotePendingCase } from "@/lib/runs";

// POST /api/corpus/promote { case_id, label? }: promote a reviewed pending case
// into the golden corpus. label (optional) corrects the provisional class and is
// validated against the known failure classes. The write logic lives in the CLI.
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as {
    case_id?: unknown;
    label?: unknown;
  };
  const caseId = typeof body.case_id === "string" ? body.case_id.trim() : "";
  if (!caseId) {
    return NextResponse.json({ error: "case_id is required." }, { status: 400 });
  }
  let label: string | undefined;
  if (typeof body.label === "string" && body.label) {
    if (!(FAILURE_CLASSES as readonly string[]).includes(body.label)) {
      return NextResponse.json({ error: "Unknown failure class." }, { status: 400 });
    }
    label = body.label;
  }
  try {
    await promotePendingCase(caseId, label);
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json(
      { error: "Could not promote the case (it may already be in the golden corpus)." },
      { status: 500 },
    );
  }
}
