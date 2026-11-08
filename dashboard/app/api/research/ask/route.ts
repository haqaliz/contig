import { NextResponse } from "next/server";

import { askResearch } from "@/lib/research";

export async function POST(request: Request): Promise<NextResponse> {
  try {
    const body = (await request.json()) as { question?: unknown };
    const question = typeof body.question === "string" ? body.question : "";
    if (!question.trim()) {
      return NextResponse.json({ error: "question is required" }, { status: 400 });
    }
    const answer = await askResearch(question);
    return NextResponse.json(answer);
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
