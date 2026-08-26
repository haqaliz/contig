import { promises as fs } from "fs";
import path from "path";

import { reproduceBundlePath } from "@/lib/reproduce";

// GET /api/reproduce/[id]/download: single-file bundle downloads for a
// third-party `contig reproduce` bundle (C8), the audit-surface counterpart of
// the first-party export route. Read-only: reproduce bundles carry no
// owner.json, so any viewer may download them -- there is no writer gate, and
// nothing here shells out. The bundle's JSON files are served as attachments
// via an allowlist param (?file=record|manifest|signature); the signed record
// itself is the auditable artifact, the source/ tree is attested by
// source_commit + source_tree_sha256 and never downloaded.
export const dynamic = "force-dynamic";

// Allowlist: query value -> file name under the bundle dir.
const FILES = {
  record: "reproduce_record.json",
  manifest: "reproduce.json",
  signature: "signature.json",
} as const;
type FileKey = keyof typeof FILES;

// The same safe-id rule InvalidRunIdError uses in lib/runs.ts (letters,
// digits, dot, underscore, dash, no leading dash). That guard is module-private
// there, so it is mirrored here: a reproduce id is the same filesystem token.
function isSafeId(value: string): boolean {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    /^[A-Za-z0-9._-]+$/.test(value) &&
    !value.startsWith("-")
  );
}

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!isSafeId(id)) {
    return Response.json({ error: `Invalid reproduce id: ${id}` }, { status: 400 });
  }

  const file = new URL(req.url).searchParams.get("file") as FileKey | null;
  if (!file || !(file in FILES)) {
    return Response.json(
      { error: `Unknown file: ${file ?? "(none)"}` },
      { status: 400 },
    );
  }

  const name = FILES[file];
  const p = path.join(reproduceBundlePath(id), name);
  try {
    const bytes = await fs.readFile(p);
    return new Response(bytes, {
      status: 200,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Disposition": `attachment; filename="${id}.${name}"`,
      },
    });
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      // Missing dir or file (a bundle may predate the manifest; a bundle
      // without signature.json must 404 honestly).
      return Response.json({ error: "File not found." }, { status: 404 });
    }
    return Response.json(
      { error: "Could not read the file." },
      { status: 500 },
    );
  }
}