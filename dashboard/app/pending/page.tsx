// The pending-review page (Server Component). It reads the auto-captured failure
// cases from disk via getPendingCorpus (the <runs_dir>/pending_corpus.jsonl file)
// and hands them to the view. No client interactivity: this is a read-only
// surface, so the fetch and the render both stay on the server.
import { PendingView } from "./pending-view";
import { getPendingCorpus } from "@/lib/runs";

// Read fresh on every request so the list reflects the current pending cases on disk.
export const dynamic = "force-dynamic";

export default async function PendingPage() {
  const cases = await getPendingCorpus();

  return <PendingView cases={cases} />;
}
