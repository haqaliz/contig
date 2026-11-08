import { NextResponse } from "next/server";

import { loadResearch } from "@/lib/research";

export async function GET(): Promise<Response> {
  const data = await loadResearch();
  if (!data?.reportHtml) {
    return NextResponse.json({ error: "report HTML not attached" }, { status: 404 });
  }
  return new Response(data.reportHtml, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}
