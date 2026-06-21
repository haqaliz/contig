// New run view (Server Component): the shell around the client launch form. The
// user describes a goal and points at their data, previews the engine's plan,
// and approves it before anything runs on their compute. The form itself is the
// only client island here.
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { LaunchForm } from "./launch-form";

// Next 16: searchParams is a Promise and must be awaited.
export default async function NewRunPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string }>;
}) {
  const { from } = await searchParams;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <Link
        href="/runs"
        className="inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All runs
      </Link>

      <PageHeader
        title="New run"
        description="Describe the goal and point at your data. Contig builds a plan (pipeline, parameters, warnings) that you approve before it runs on your compute."
      />

      <LaunchForm from={from} />
    </div>
  );
}
