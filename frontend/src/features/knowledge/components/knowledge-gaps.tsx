"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

type Gap = { id: string; question: string; reason: string; status: string };
type GapPage = { items: Gap[] };

export function KnowledgeGaps() {
  const gaps = useQuery({
    queryKey: ["knowledge-gaps"],
    queryFn: () => api<GapPage>("/knowledge/gaps"),
  });
  return (
    <section className="rounded-xl border border-border p-5 space-y-3">
      <h2 className="text-lg font-semibold">Unanswered customer questions</h2>
      <p className="text-sm text-muted-foreground">
        Missing knowledge detected from widget AI replies. FAQ suggestions require review before publishing.
      </p>
      {gaps.isLoading && <p className="text-sm">Loading knowledge gaps…</p>}
      {gaps.isError && <p role="alert" className="text-sm text-destructive">Could not load knowledge gaps.</p>}
      {gaps.data?.items.length === 0 && <p className="text-sm text-muted-foreground">No knowledge gaps recorded yet.</p>}
      <ul className="divide-y divide-border">
        {gaps.data?.items.map((gap) => (
          <li key={gap.id} className="py-3">
            <p className="text-sm font-medium">{gap.question}</p>
            <p className="text-xs text-muted-foreground">{gap.reason.replaceAll("_", " ")} · {gap.status}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
