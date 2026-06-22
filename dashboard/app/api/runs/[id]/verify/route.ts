import { NextResponse } from "next/server";

import { getOutputVerification, InvalidRunIdError } from "@/lib/runs";

// POST /api/runs/[id]/verify: re-check a run's outputs against its recorded
// checksums. The dashboard never hashes files itself; this shells out to
// `contig verify <id> --json` (CONTIG_DISPATCH_CMD), which validates the run id,
// re-hashes the recorded output files, and reports {ok, changed, missing}. A bad
// id is 400; an unavailable or unparseable CLI is 502 (the verdict is unknown,
// not a clean pass). Re-run on every request, never cached.
export const dynamic = "force-dynamic";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const report = await getOutputVerification(id);
    if (!report) {
      return NextResponse.json(
        { error: "Could not verify the outputs." },
        { status: 502 },
      );
    }
    return NextResponse.json(report, { status: 200 });
  } catch (err) {
    if (err instanceof InvalidRunIdError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    return NextResponse.json(
      { error: "Could not verify the outputs." },
      { status: 500 },
    );
  }
}
