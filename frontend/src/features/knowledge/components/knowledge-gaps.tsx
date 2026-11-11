"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

type Group = { representative: string; count: number; gap_ids: string[] };
type GroupPage = { items: Group[] };

export function KnowledgeGaps() {
  const queryClient = useQueryClient();
  const review = useMutation({
    mutationFn: ({ gap_ids, status }: { gap_ids: string[]; status: "resolved" | "dismissed" }) => api<{ updated: number }>("/knowledge/gaps/groups/review", { method: "POST", body: JSON.stringify({ gap_ids, status }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["knowledge-gap-groups"] }),
  });
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
      {review.isError && <p role="alert" className="text-sm text-destructive">Could not update question status.</p>}
      <ul className="divide-y divide-border">
        {groups.data?.items.map((group) => (
          <li key={group.gap_ids[0]} className="py-3 flex flex-wrap items-start justify-between gap-3">
            <p className="text-sm font-medium">{group.representative}</p>
            <div className="flex flex-wrap items-center gap-2"><span className="shrink-0 text-xs text-muted-foreground">{group.count} {group.count === 1 ? "question" : "questions"}</span><button type="button" disabled={review.isPending} onClick={() => review.mutate({ gap_ids: group.gap_ids, status: "resolved" })} className="rounded border border-border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50">Resolve</button><button type="button" disabled={review.isPending} onClick={() => review.mutate({ gap_ids: group.gap_ids, status: "dismissed" })} className="rounded border border-border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50">Dismiss</button></div>
          </li>
        ))}
      </ul>
    </section>
  );
}
