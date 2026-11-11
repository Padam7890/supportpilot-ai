"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { knowledgeBaseKey, listKnowledgeBases } from "../api/knowledge-base-api";
import { knowledgeKeys } from "../api/knowledge-api";

type Group = { representative: string; count: number; gap_ids: string[] };
type GroupPage = { items: Group[]; has_more: boolean };
type Draft = { group: Group; question: string; answer: string; knowledgeBaseId: string };

export function KnowledgeGaps() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [notice, setNotice] = useState("");
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const bases = useQuery({ queryKey: knowledgeBaseKey, queryFn: listKnowledgeBases });
  const activeBases = bases.data?.items.filter((base) => base.status === "active") ?? [];
  const review = useMutation({
    mutationFn: ({ gap_ids, status }: { gap_ids: string[]; status: "resolved" | "dismissed" }) =>
      api<{ updated: number }>("/knowledge/gaps/groups/review", { method: "POST", body: JSON.stringify({ gap_ids, status }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["knowledge-gap-groups"] }),
  });
  const publish = useMutation({
    mutationFn: async (item: Draft) => {
      const question = item.question.trim();
      const answer = item.answer.trim();
      if (!question || !answer || !item.knowledgeBaseId) throw new Error("Enter a verified answer and select a knowledge base.");
      if (question.length > 1000 || answer.length > 10000) throw new Error("FAQ content is too long.");
      return api<{ document_id: string; status: string; already_submitted: boolean }>("/knowledge/gaps/groups/publish", {
        method: "POST",
        body: JSON.stringify({
          gap_ids: item.group.gap_ids,
          knowledge_base_id: item.knowledgeBaseId,
          question,
          answer,
        }),
      });
    },
    onSuccess: async (document) => {
      setNotice(document.already_submitted ? "This FAQ was already submitted. Check its ingestion status before resolving." : `FAQ submitted atomically with its review history (status: ${document.status}). Verify processing before resolving.`);
      setDraft(null);
      await Promise.all([queryClient.invalidateQueries({ queryKey: knowledgeKeys.documents }), queryClient.invalidateQueries({ queryKey: ["knowledge-gap-reviews"] })]);
    },
  });
  const reviews = useQuery({
    queryKey: ["knowledge-gap-reviews"],
    queryFn: () => api<Array<{ gap_id: string; document_id: string; status: string }>>("/knowledge/gaps/reviews"),
  });
  const groups = useQuery({
    queryKey: ["knowledge-gap-groups", page],
    queryFn: () => api<GroupPage>(`/knowledge/gaps/groups?limit=${pageSize}&offset=${page * pageSize}`),
    retry: false,
  });
  const openDraft = (group: Group) => {
    setNotice("");
    setDraft({
      group,
      question: group.representative,
      answer: "",
      knowledgeBaseId: activeBases.find((base) => base.is_default)?.id ?? activeBases[0]?.id ?? "",
    });
  };
  return (
    <section className="rounded-xl border border-border p-5 space-y-3">
      <h2 className="text-lg font-semibold">Unanswered customer questions</h2>
      <p className="text-sm text-muted-foreground">
        Review similar customer questions and publish only answers you have verified.
      </p>
      {groups.isLoading && <p className="text-sm">Grouping unanswered questions…</p>}
      {groups.isError && <p role="alert" className="text-sm text-destructive">Semantic grouping is unavailable. Check embedding provider configuration.</p>}
      {groups.data?.items.length === 0 && <p className="text-sm text-muted-foreground">No knowledge gaps recorded yet.</p>}
      {review.isError && <p role="alert" className="text-sm text-destructive">Could not update question status.</p>}
      {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
      {reviews.data && reviews.data.length > 0 && <p className="text-xs text-muted-foreground">FAQ submissions: {reviews.data.filter((r) => r.status === "ready").length} ready, {reviews.data.filter((r) => r.status !== "ready").length} pending or failed. Status is refreshed when this page loads.</p>}
      <ul className="divide-y divide-border">
        {groups.data?.items.map((group) => (
          <li key={group.gap_ids[0]} className="py-3 flex flex-wrap items-start justify-between gap-3">
            <p className="text-sm font-medium">{group.representative}</p>
            <div className="flex flex-wrap items-center gap-2">
              <span className="shrink-0 text-xs text-muted-foreground">{group.count} {group.count === 1 ? "question" : "questions"}</span>
              <button type="button" onClick={() => openDraft(group)} className="rounded border border-border px-2 py-1 text-xs hover:bg-accent">Review FAQ</button>
              <button type="button" disabled={review.isPending} onClick={() => review.mutate({ gap_ids: group.gap_ids, status: "resolved" })} className="rounded border border-border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50">Resolve</button>
              <button type="button" disabled={review.isPending} onClick={() => review.mutate({ gap_ids: group.gap_ids, status: "dismissed" })} className="rounded border border-border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50">Dismiss</button>
            </div>
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between gap-3 text-sm">
        <button type="button" disabled={page === 0 || groups.isFetching} onClick={() => setPage((current) => Math.max(0, current - 1))} className="rounded border border-border px-3 py-1 disabled:opacity-50">Previous</button>
        <span>Page {page + 1}</span>
        <button type="button" disabled={groups.isFetching || !groups.data?.has_more} onClick={() => setPage((current) => current + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-50">Next</button>
      </div>
      {draft && (
        <div className="space-y-3 rounded-lg border border-border bg-card p-4" aria-label="FAQ review editor">
          <h3 className="font-semibold">Review and publish FAQ</h3>
          <p className="text-xs text-muted-foreground">Answers are never AI-generated here. Confirm facts against store policies before submitting.</p>
          <label className="block space-y-1 text-sm">
            <span>Question</span>
            <textarea maxLength={1000} rows={2} value={draft.question} onChange={(event) => setDraft({ ...draft, question: event.target.value })} className="w-full rounded border border-border bg-background p-2" />
          </label>
          <label className="block space-y-1 text-sm">
            <span>Verified answer</span>
            <textarea maxLength={10000} rows={5} value={draft.answer} onChange={(event) => setDraft({ ...draft, answer: event.target.value })} placeholder="Enter the approved store policy or answer" className="w-full rounded border border-border bg-background p-2" />
          </label>
          <label className="block space-y-1 text-sm">
            <span>Knowledge base</span>
            <select value={draft.knowledgeBaseId} onChange={(event) => setDraft({ ...draft, knowledgeBaseId: event.target.value })} className="w-full rounded border border-border bg-background p-2">
              <option value="">Select knowledge base</option>
              {activeBases.map((base) => <option key={base.id} value={base.id}>{base.name}</option>)}
            </select>
          </label>
          {publish.isError && <p role="alert" className="text-sm text-destructive">{publish.error instanceof Error ? publish.error.message : "FAQ upload failed"}</p>}
          <div className="flex gap-2">
            <button type="button" disabled={publish.isPending || !draft.question.trim() || !draft.answer.trim() || !draft.knowledgeBaseId} onClick={() => publish.mutate(draft)} className="rounded bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">Approve and submit to knowledge base</button>
            <button type="button" disabled={publish.isPending} onClick={() => setDraft(null)} className="rounded border border-border px-3 py-2 text-sm">Cancel</button>
          </div>
        </div>
      )}
    </section>
  );
}
