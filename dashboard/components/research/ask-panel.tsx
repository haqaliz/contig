"use client";

import { useState } from "react";

interface Citation {
  label: string;
  path: string;
  sha256: string;
  detail?: string;
}

interface Answer {
  intent: string;
  answer: string;
  citations: Citation[];
  confidence: string;
  actions: string[];
}

export function AskPanel() {
  const [question, setQuestion] = useState("what is the verdict?");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const response = await fetch("/api/research/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const payload = (await response.json()) as Answer | { error?: string };
      if (!response.ok || "error" in payload) {
        throw new Error(("error" in payload && payload.error) || "ask failed");
      }
      setAnswer(payload as Answer);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          className="min-w-0 flex-1 rounded-md border bg-background px-3 py-2 text-sm"
          placeholder="Ask about the verdict, QC, repairs, variants, readiness, or report"
          aria-label="Question"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background disabled:opacity-50"
        >
          {loading ? "Asking…" : "Ask"}
        </button>
      </form>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      {answer ? (
        <div className="space-y-3 rounded-lg border bg-muted/30 p-4">
          <p className="whitespace-pre-wrap text-sm">{answer.answer}</p>
          {answer.citations.length > 0 ? (
            <div>
              <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Sources</h4>
              <ul className="mt-1 space-y-1 text-xs">
                {answer.citations.map((citation) => (
                  <li key={`${citation.label}-${citation.path}`}>
                    <span className="font-medium">{citation.label}</span>:{" "}
                    <code className="font-mono">{citation.path}</code>{" "}
                    <span className="text-muted-foreground">(sha256 {citation.sha256})</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {answer.actions.length > 0 ? (
            <div>
              <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Suggested actions</h4>
              <ul className="mt-1 space-y-1 text-xs">
                {answer.actions.map((action) => (
                  <li key={action}>
                    <code className="font-mono">{action}</code>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
