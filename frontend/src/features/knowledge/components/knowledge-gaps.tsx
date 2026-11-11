"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { knowledgeBaseKey, listKnowledgeBases } from "../api/knowledge-base-api";
import { knowledgeKeys } from "../api/knowledge-api";

type Group = { representative: string; count: number; gap_ids: string[] };
type GroupPage = { items: Group[]; has_more: boolean };
type DurableGroup = { id: string; representative: string; gap_ids: string[] };
type Draft = { group: Group; question: string; answer: string; knowledgeBaseId: string };

export function KnowledgeGaps() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [notice, setNotice] = useState("");
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const [targetGroupId, setTargetGroupId] = useState("");
  const [selectedGapIds, setSelectedGapIds] = useState<string[]>([]);
  const [threshold, setThreshold] = useState(0.86);
  const durable = useQuery({ queryKey: ["knowledge-gap-durable"], queryFn: () => api<DurableGroup[]>("/knowledge/gaps/durable-groups?limit=100") });
  const refreshGroups = async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ["knowledge-gap-durable"] }), queryClient.invalidateQueries({ queryKey: ["knowledge-gap-groups"] })]); };
  const assign = useMutation({ mutationFn: () => api<{assigned:number;created:number}>("/knowledge/gaps/durable-groups/auto-assign", { method:"POST", body:JSON.stringify({limit:100,threshold}) }), onSuccess: async (result) => { setNotice(`Assigned ${result.assigned} questions and created ${result.created} groups.`); await refreshGroups(); } });
  const move = useMutation({ mutationFn: () => api<{moved:number}>(`/knowledge/gaps/durable-groups/${targetGroupId}/members`, { method:"POST", body:JSON.stringify({gap_ids:selectedGapIds}) }), onSuccess: async () => { setSelectedGapIds([]); setNotice("Selected questions moved."); await refreshGroups(); } });
  const remove = useMutation({ mutationFn: (id:string) => api<void>(`/knowledge/gaps/durable-groups/${id}`, { method:"DELETE" }), onSuccess: async () => { setNotice("Group deleted; questions retained."); await refreshGroups(); } });
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
      <div className="space-y-3 rounded-lg border border-border p-3">
        <h3 className="text-sm font-semibold">Persistent semantic groups</h3>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label>Similarity threshold <input aria-label="Similarity threshold" type="number" min="0.01" max="1" step="0.01" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} className="w-20 rounded border border-border bg-background px-2 py-1" /></label>
          <button type="button" disabled={assign.isPending || threshold <= 0 || threshold > 1} onClick={() => assign.mutate()} className="rounded border border-border px-3 py-1 disabled:opacity-50">Auto-group next 100 questions</button>
        </div>
        <p className="text-xs text-muted-foreground">Select individual questions to split into another group, or select all questions in a group to merge them into the target group.</p>
        {durable.data?.map((group) => <div key={group.id} className="rounded border border-border p-2 text-sm space-y-2">
          <div className="flex flex-wrap justify-between gap-2"><span className="font-medium">{group.representative} ({group.gap_ids.length})</span><button type="button" disabled={remove.isPending} onClick={() => { if (window.confirm("Delete this group? The questions will be kept.")) remove.mutate(group.id); }} className="rounded border border-border px-2 py-1 text-xs">Delete group</button></div>
          <button type="button" className="text-xs underline" onClick={() => setSelectedGapIds(group.gap_ids)}>Select all questions in this group</button>
          <div className="flex flex-wrap gap-2">{group.gap_ids.map((id) => <label key={id} className="flex items-center gap-1 text-xs"><input type="checkbox" checked={selectedGapIds.includes(id)} onChange={(event) => setSelectedGapIds((old) => event.target.checked ? [...old.filter((value) => value !== id), id] : old.filter((value) => value !== id))} />{id.slice(0,8)}</label>)}</div>
        </div>)}
        <div className="flex flex-wrap gap-2 items-center"><select aria-label="Target group" className="rounded border border-border bg-background px-2 py-1 text-sm" value={targetGroupId} onChange={(event) => setTargetGroupId(event.target.value)}><option value="">Choose target group</option>{durable.data?.map((group) => <option key={group.id} value={group.id}>{group.representative.slice(0,65)}</option>)}</select><button type="button" disabled={!targetGroupId || !selectedGapIds.length || move.isPending} onClick={() => move.mutate()} className="rounded border border-border px-3 py-1 text-sm disabled:opacity-50">Move selected questions</button></div>
        {(assign.isError || move.isError || remove.isError || durable.isError) && <p role="alert" className="text-sm text-destructive">Could not update persistent groups. Refresh and retry.</p>}
      </div>
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
