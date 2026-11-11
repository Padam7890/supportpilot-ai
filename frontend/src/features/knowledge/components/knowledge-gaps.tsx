"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

type Group = { representative: string; count: number; gap_ids: string[] };
type GroupPage = { items: Group[] };

export function KnowledgeGaps() {
  const groups = useQuery({
    queryKey: ["knowledge-gap-groups"],
    queryFn: () => api<GroupPage>("/knowledge/gaps/groups"),
    retry: false,
  });
  return (
    <section className="rounded-xl border border-border p-5 space-y-3">
      <h2 className="text-lg font-semibold">Unanswered customer questions</h2>
      <p className="text-sm text-muted-foreground">
        Similar missing-knowledge questions are grouped for review. No FAQ is published automatically.
      </p>
      {groups.isLoading && <p className="text-sm">Grouping unanswered questions…</p>}
      {groups.isError && <p role="alert" className="text-sm text-destructive">
        Semantic grouping is unavailable. Check the embedding provider configuration.
      </p>}
      {groups.data?.items.length === 0 && <p className="text-sm text-muted-foreground">No knowledge gaps recorded yet.</p>}
      <ul className="divide-y divide-border">
        {groups.data?.items.map((group) => (
          <li key={group.gap_ids[0]} className="py-3 flex items-start justify-between gap-3">
            <p className="text-sm font-medium">{group.representative}</p>
            <span className="shrink-0 text-xs text-muted-foreground">{group.count} {group.count === 1 ? "question" : "questions"}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
