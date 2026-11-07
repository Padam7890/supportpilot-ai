"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Archive, BookOpen, ChevronLeft, ChevronRight, FileText, History, LoaderCircle, Plus, RotateCcw, RotateCw, Search, Star, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input, Select } from "@/components/ui/input";
import { StatusAlert } from "@/components/ui/status-alert";
import { formatDateTime } from "@/lib/utils";
import { currentUserQueryKey, getCurrentUser } from "@/features/auth/api/auth-api";
import { aiAgentsKey, listAIAgents } from "@/features/ai/api/ai-agent-api";
import { deleteKnowledgeDocument, isKnowledgeDocumentProcessing, KNOWLEDGE_PROCESSING_POLL_INTERVAL_MS, knowledgeKeys, listKnowledgeDocuments, moveKnowledgeDocument, KNOWLEDGE_DOCUMENT_PAGE_SIZE, reprocessKnowledgeDocument, searchKnowledge, uploadKnowledgeDocument } from "../api/knowledge-api";
import type { KnowledgeDocument } from "../types/knowledge.types";
import { archiveKnowledgeBase, createKnowledgeBase, knowledgeBaseKey, listKnowledgeBaseAudit, listKnowledgeBases, makeDefaultKnowledgeBase, restoreKnowledgeBase, updateKnowledgeBase } from "../api/knowledge-base-api";

export function KnowledgeLibrary() {
  const client = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [queryText, setQueryText] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [searchScope, setSearchScope] = useState("current");
  const [selectedBaseId, setSelectedBaseId] = useState<string>();
  const [historyBaseId, setHistoryBaseId] = useState<string>();
  const [historyOffset, setHistoryOffset] = useState(0);
  const [documentPage, setDocumentPage] = useState({ baseId: "", offset: 0 });
  const [archiveBaseId, setArchiveBaseId] = useState<string>();
  const [newBaseName, setNewBaseName] = useState("");
  const user = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const canManage = ["owner", "admin"].includes(user.data?.role ?? "");
  const bases = useQuery({ queryKey: knowledgeBaseKey, queryFn: listKnowledgeBases });
  const agents = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents });
  const activeBases = bases.data?.items.filter((base) => base.status === "active") ?? [];
  const archivedBases = bases.data?.items.filter((base) => base.status === "archived") ?? [];
  const selectedBaseIsActive = activeBases.some((base) => base.id === selectedBaseId);
  const effectiveBaseId = (selectedBaseIsActive ? selectedBaseId : undefined)
    ?? activeBases.find((base) => base.is_default)?.id
    ?? activeBases[0]?.id;
  const selectedBase = activeBases.find((base) => base.id === effectiveBaseId);
  const historyBase = bases.data?.items.find((base) => base.id === historyBaseId)
    ?? selectedBase;
  const baseAudit = useQuery({
    queryKey: ["knowledge-base-audit", historyBase?.id, historyOffset],
    queryFn: () => listKnowledgeBaseAudit(historyBase?.id ?? "", historyOffset),
    enabled: canManage && Boolean(historyBase?.id),
  });
  const historyPageLimit = baseAudit.data?.limit ?? 10;
  const baseToArchive = activeBases.find((base) => base.id === archiveBaseId);
  const botsUsingArchiveBase = baseToArchive
    ? agents.data?.items.filter((agent) => (agent.knowledge_base_ids ?? []).includes(baseToArchive.id)) ?? []
    : [];
  const activeBotsUsingArchiveBase = botsUsingArchiveBase.filter((agent) => agent.status === "active");
  const assignedAgents = effectiveBaseId
    ? agents.data?.items.filter((agent) => (agent.knowledge_base_ids ?? []).includes(effectiveBaseId)) ?? []
    : [];
  const activeAssignedAgents = assignedAgents.filter((agent) => agent.status === "active");
  const inactiveAssignedAgentCount = assignedAgents.length - activeAssignedAgents.length;
  const documentOffset = documentPage.baseId === effectiveBaseId ? documentPage.offset : 0;
  const documents = useQuery({
    queryKey: [...knowledgeKeys.documents, effectiveBaseId, documentOffset],
    queryFn: () => listKnowledgeDocuments(effectiveBaseId, documentOffset),
    enabled: bases.isSuccess && Boolean(effectiveBaseId),
    refetchInterval: (query) => query.state.data?.items.some(isKnowledgeDocumentProcessing)
      ? KNOWLEDGE_PROCESSING_POLL_INTERVAL_MS
      : false,
    refetchIntervalInBackground: false,
  });
  const activeSearchScope = searchScope === "current" || searchScope === "all" || activeBases.some((base) => base.id === searchScope)
    ? searchScope
    : "current";
  const searchAllBases = activeSearchScope === "all";
  const searchBaseId = searchAllBases
    ? undefined
    : activeSearchScope === "current"
      ? effectiveBaseId
      : activeBases.find((base) => base.id === activeSearchScope)?.id ?? effectiveBaseId;
  const results = useQuery({
    queryKey: [...knowledgeKeys.search(searchTerm), searchBaseId ?? "all-active-bases"],
    queryFn: () => searchKnowledge(searchTerm, searchBaseId),
    enabled: bases.isSuccess && searchTerm.length >= 2 && (searchAllBases || Boolean(effectiveBaseId)),
  });
  const upload = useMutation({ mutationFn: uploadKnowledgeDocument, onSuccess: async () => { if (fileInput.current) fileInput.current.value = ""; setDocumentPage({ baseId: effectiveBaseId ?? "", offset: 0 }); await client.invalidateQueries({ queryKey: knowledgeKeys.documents }); } });
  const refreshBaseAudit = () => client.invalidateQueries({ queryKey: ["knowledge-base-audit"] });
  const createBase = useMutation({ mutationFn: () => createKnowledgeBase({ name: newBaseName.trim(), description: null }), onSuccess: async (base) => { setNewBaseName(""); setHistoryOffset(0); await client.invalidateQueries({ queryKey: knowledgeBaseKey }); setSelectedBaseId(base.id); setHistoryBaseId(base.id); await refreshBaseAudit(); } });
  const archiveBase = useMutation({ mutationFn: archiveKnowledgeBase, onSuccess: async (_, baseId) => { setSelectedBaseId(undefined); setHistoryBaseId(baseId); setHistoryOffset(0); setArchiveBaseId(undefined); await client.invalidateQueries({ queryKey: knowledgeBaseKey }); await refreshBaseAudit(); } });
  const restoreBase = useMutation({ mutationFn: restoreKnowledgeBase, onSuccess: async (base) => { setSelectedBaseId(base.id); setHistoryBaseId(base.id); setHistoryOffset(0); await client.invalidateQueries({ queryKey: knowledgeBaseKey }); await refreshBaseAudit(); } });
  const makeDefaultBase = useMutation({ mutationFn: makeDefaultKnowledgeBase, onSuccess: async () => { await client.invalidateQueries({ queryKey: knowledgeBaseKey }); await refreshBaseAudit(); } });
  const updateBase = useMutation({
    mutationFn: ({ id, name, description }: { id: string; name: string; description: string | null }) =>
      updateKnowledgeBase(id, { name, description }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: knowledgeBaseKey }); await refreshBaseAudit(); },
  });
  const reprocess = useMutation({
    mutationFn: reprocessKnowledgeDocument,
    onSuccess: async (_document, documentId) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: knowledgeKeys.documents }),
        client.invalidateQueries({ queryKey: ["knowledge-document", documentId] }),
      ]);
    },
  });
  const remove = useMutation({ mutationFn: deleteKnowledgeDocument, onSuccess: () => client.invalidateQueries({ queryKey: knowledgeKeys.documents }) });
  const move = useMutation({
    mutationFn: ({ documentId, knowledgeBaseId }: { documentId: string; knowledgeBaseId: string }) =>
      moveKnowledgeDocument(documentId, knowledgeBaseId),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: knowledgeKeys.documents }),
        client.invalidateQueries({ queryKey: ["knowledge-search"] }),
        refreshBaseAudit(),
      ]);
    },
  });
  const writeError = upload.error ?? reprocess.error ?? remove.error ?? move.error ?? createBase.error ?? archiveBase.error ?? restoreBase.error ?? makeDefaultBase.error ?? updateBase.error;

  useEffect(() => {
    const visibilityChanged = () => {
      if (document.visibilityState === "visible") void client.invalidateQueries({ queryKey: knowledgeKeys.documents });
    };
    document.addEventListener("visibilitychange", visibilityChanged);
    return () => document.removeEventListener("visibilitychange", visibilityChanged);
  }, [client]);

  useEffect(() => {
    if (documents.isSuccess && documentOffset > 0 && documents.data.items.length === 0 && documents.data.total <= documentOffset) {
      setDocumentPage({ baseId: effectiveBaseId ?? "", offset: Math.max(0, documentOffset - KNOWLEDGE_DOCUMENT_PAGE_SIZE) });
    }
  }, [documents.data, documents.isSuccess, documentOffset, effectiveBaseId]);

  const documentRange = documents.data
    ? documents.data.items.length > 0
      ? `${documentOffset + 1}–${documentOffset + documents.data.items.length} of ${documents.data.total}`
      : `0 of ${documents.data.total}`
    : "Document count is loading";

  return <div className="space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-sm font-semibold text-blue-700">Knowledge library</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Knowledge bases</h1><p className="mt-2 max-w-2xl text-sm text-slate-500">Organize support documents into libraries and assign them to AI bots.</p></div>
      {canManage && <Button onClick={() => fileInput.current?.click()} disabled={upload.isPending || !bases.isSuccess || !selectedBase || !effectiveBaseId}><Upload size={16}/>{upload.isPending ? "Uploading…" : "Upload document"}</Button>}
      {canManage && <input ref={fileInput} type="file" accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" className="sr-only" aria-label="Choose a PDF, text, or Markdown document" onChange={(event) => { const file = event.target.files?.[0]; if (file && bases.isSuccess && selectedBase && effectiveBaseId) upload.mutate({ file, knowledgeBaseId: effectiveBaseId }); }}/>}
    </header>
    {!user.isPending && user.data && !canManage && <p role="status" className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">Your role has read-only access to knowledge settings.</p>}
    {writeError && <StatusAlert tone="error">{writeError.message}</StatusAlert>}
    <Panel><PanelHeader title="Knowledge bases" description="Each bot can use one or more active bases." action={<BookOpen size={17} className="text-slate-400"/>}/><PanelBody className="space-y-4">
      {canManage && <form className="flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); if (newBaseName.trim()) createBase.mutate(); }}><Input aria-label="New knowledge base name" placeholder="New knowledge base name" value={newBaseName} onChange={(event) => setNewBaseName(event.target.value)}/><Button type="submit" disabled={!newBaseName.trim() || createBase.isPending}><Plus size={15}/>Create base</Button></form>}
      {bases.isPending && <p role="status" className="text-sm text-slate-500">Loading knowledge bases…</p>}{bases.isError && <p role="alert" className="text-sm text-red-700">Knowledge bases could not be loaded.</p>}
      {activeBases.length > 0 && <div className="flex flex-wrap gap-2" role="group" aria-label="Knowledge bases">{activeBases.map((base) => <div key={base.id} className={`flex items-center gap-1 rounded-xl border px-2 py-1 ${effectiveBaseId === base.id ? "border-blue-300 bg-blue-50" : "border-slate-200"}`}><button type="button" aria-label={`${base.name}${base.is_default ? ", default" : ""}: ${base.ready_document_count} ready of ${base.document_count} documents`} aria-pressed={effectiveBaseId === base.id} onClick={() => { setSelectedBaseId(base.id); setHistoryBaseId(base.id); setHistoryOffset(0); setSearchTerm(""); }} className="rounded-lg px-2 py-1.5 text-left text-sm font-medium text-slate-800"><span className="block">{base.name}{base.is_default ? " · default" : ""}</span><span className={`mt-0.5 block text-[11px] font-normal ${base.ready_document_count > 0 ? "text-emerald-700" : base.processing_document_count > 0 ? "text-blue-700" : "text-amber-700"}`}>{base.ready_document_count} ready{base.processing_document_count > 0 ? ` · ${base.processing_document_count} processing` : base.document_count === 0 ? " · empty" : ""}</span></button>{canManage && !base.is_default && <button type="button" aria-label={`Make ${base.name} the default knowledge base`} title="Make default for requests without a selected base" onClick={() => makeDefaultBase.mutate(base.id)} disabled={makeDefaultBase.isPending} className="rounded-lg p-1.5 text-slate-500 hover:bg-white hover:text-blue-700"><Star size={14}/></button>}{canManage && !base.is_default && <button type="button" aria-label={`Archive ${base.name}`} title="Archive base" onClick={() => setArchiveBaseId(base.id)} disabled={archiveBase.isPending} className="rounded-lg p-1.5 text-slate-500 hover:bg-white hover:text-slate-900"><Archive size={14}/></button>}</div>)}</div>}
      {canManage && activeBases.length > 0 && <p className="text-xs text-slate-500">The default base is selected for uploads and knowledge searches without a base selection. AI bots continue to use their assigned bases.</p>}
      {effectiveBaseId && <section aria-labelledby="knowledge-base-usage-title" className="rounded-xl border border-blue-100 bg-blue-50/60 p-3"><h3 id="knowledge-base-usage-title" className="text-xs font-semibold text-blue-950">AI bot access</h3>{agents.isPending && <p role="status" className="mt-1 text-xs text-slate-600">Loading bot assignments…</p>}{agents.isError && <p role="alert" className="mt-1 text-xs text-red-700">Bot assignments could not be loaded.</p>}{agents.isSuccess && (activeAssignedAgents.length > 0 ? <p className="mt-1 text-xs leading-5 text-slate-700">Used by {activeAssignedAgents.length === 1 ? "active bot" : "active bots"}: {activeAssignedAgents.map((agent) => agent.name).join(", ")}.</p> : <p className="mt-1 text-xs leading-5 text-slate-700">No active AI bot uses this base yet. Assign it from <Link href="/dashboard/ai/agents" className="font-semibold text-blue-800 underline">AI Bots</Link> to include these sources in answers.</p>)}{inactiveAssignedAgentCount > 0 && <p className="mt-1 text-xs text-slate-600">{inactiveAssignedAgentCount} inactive {inactiveAssignedAgentCount === 1 ? "bot is" : "bots are"} also assigned; inactive bots cannot use this base.</p>}</section>}
      {baseToArchive && (
        <ConfirmDialog
          open
          onOpenChange={(open) => {
            if (!open && !archiveBase.isPending) setArchiveBaseId(undefined);
          }}
          title={`Archive “${baseToArchive.name}”?`}
          description="Its documents and history will be preserved, but retrieval stops using this base until it is restored."
          confirmLabel="Archive base"
          pendingLabel="Archiving…"
          cancelLabel="Keep active"
          confirmVariant="destructive"
          pending={archiveBase.isPending}
          disabled={agents.isPending || agents.isError}
          onConfirm={() => archiveBase.mutate(baseToArchive.id)}
        >
          {agents.isPending && <p className="text-sm text-muted-foreground">Checking bot assignments…</p>}
          {agents.isError && (
            <StatusAlert tone="error" onRetry={() => agents.refetch()}>
              Bot assignments could not be checked, so archiving is paused.
            </StatusAlert>
          )}
          {agents.isSuccess && (
            activeBotsUsingArchiveBase.length > 0 ? (
              <StatusAlert tone="warning" title="Active bots will lose these sources:">
                <ul className="mt-1 list-inside list-disc">
                  {activeBotsUsingArchiveBase.map((agent) => (
                    <li key={agent.id}>{agent.name}</li>
                  ))}
                </ul>
              </StatusAlert>
            ) : (
              <p className="text-sm text-muted-foreground">No active bot is currently assigned to this base.</p>
            )
          )}
          {archiveBase.isError && (
            <StatusAlert tone="error">{archiveBase.error.message || "The knowledge base could not be archived."}</StatusAlert>
          )}
        </ConfirmDialog>
      )}
      {activeBases.length === 0 && !bases.isPending && !bases.isError && <p className="text-sm text-slate-500">No active knowledge bases are available.</p>}
      {bases.isError && <button type="button" className="text-sm font-semibold text-blue-700 underline" onClick={() => bases.refetch()}>Retry loading knowledge bases</button>}
      {canManage && selectedBase && <KnowledgeBaseDetailsForm key={selectedBase.id} base={selectedBase} busy={updateBase.isPending} saved={updateBase.isSuccess} onSave={(values) => updateBase.mutate(values)}/>}
      {canManage && historyBase && <section aria-labelledby="knowledge-base-history-title" className="space-y-3 border-t border-slate-100 pt-4"><div className="flex items-center gap-2"><History size={16} className="text-slate-500"/><div><h3 id="knowledge-base-history-title" className="text-sm font-semibold text-slate-800">Recent changes · {historyBase.name}</h3><p className="text-xs text-slate-500">Configuration and source moves that affect this base.</p></div></div>{baseAudit.isPending ? <p role="status" className="text-sm text-slate-500">Loading history…</p> : baseAudit.isError ? <div role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><p>History could not be loaded.</p><button type="button" className="mt-1 font-semibold underline" onClick={() => baseAudit.refetch()}>Retry</button></div> : baseAudit.data?.items.length ? <ol className="space-y-2">{baseAudit.data.items.map((event) => <li key={event.id} className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 rounded-lg border border-slate-200 px-3 py-2"><div className="min-w-0"><p className="text-sm font-medium text-slate-700">{knowledgeBaseAuditLabel(event.event_type, event.details, event.knowledge_base_id)}</p><p className="mt-0.5 text-xs text-slate-500">{event.actor_name}</p></div><time className="shrink-0 text-xs text-slate-500">{formatDateTime(event.created_at)}</time></li>)}</ol> : <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-500">No changes recorded yet.</p>}{baseAudit.data && baseAudit.data.total > baseAudit.data.limit && <nav aria-label="Knowledge base history pagination" className="flex items-center justify-between gap-3"><p className="text-xs text-slate-500">Showing {historyOffset + 1}–{Math.min(historyOffset + baseAudit.data.items.length, baseAudit.data.total)} of {baseAudit.data.total}</p><div className="flex gap-2"><Button type="button" size="sm" variant="secondary" disabled={historyOffset === 0} onClick={() => setHistoryOffset((offset) => Math.max(0, offset - historyPageLimit))}><ChevronLeft size={14}/>Newer</Button><Button type="button" size="sm" variant="secondary" disabled={historyOffset + baseAudit.data.limit >= baseAudit.data.total} onClick={() => setHistoryOffset((offset) => offset + historyPageLimit)}>Older<ChevronRight size={14}/></Button></div></nav>}</section>}
      {archivedBases.length > 0 && <section aria-labelledby="archived-bases-title" className="space-y-2 border-t border-slate-100 pt-4"><div><h3 id="archived-bases-title" className="text-sm font-semibold text-slate-800">Archived knowledge bases</h3><p className="mt-1 text-xs text-slate-500">Archived sources are preserved but excluded from AI retrieval. Restoring a base makes it available to bots that still have it assigned.</p></div><ul className="space-y-2">{archivedBases.map((base) => <li key={base.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5"><div className="min-w-0"><p className="truncate text-sm font-medium text-slate-700">{base.name}</p>{base.description && <p className="mt-0.5 truncate text-xs text-slate-500">{base.description}</p>}</div>{canManage && <Button type="button" size="sm" variant="ghost" onClick={() => { setHistoryBaseId(base.id); setHistoryOffset(0); }}>View history</Button>}{canManage && <Button type="button" size="sm" variant="secondary" disabled={restoreBase.isPending} onClick={() => restoreBase.mutate(base.id)}><RotateCcw size={14}/>{restoreBase.isPending ? "Restoring…" : "Restore"}</Button>}</li>)}</ul></section>}
    </PanelBody></Panel>
    <Panel><PanelHeader title="Search your sources" description={searchAllBases ? "Search ready documents across all active knowledge bases." : searchBaseId ? `Search within ${activeBases.find((base) => base.id === searchBaseId)?.name ?? "the selected base"}.` : "Select a knowledge base to search."}/><PanelBody><form className="flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); setSearchTerm(queryText.trim()); }}><Input aria-label="Search documents" placeholder="Search policies, procedures, product details…" value={queryText} onChange={(event) => setQueryText(event.target.value)} className="min-w-48 flex-1"/><Select aria-label="Search scope" value={activeSearchScope} onChange={(event) => setSearchScope(event.target.value)} className="w-auto min-w-40"><option value="current">Current base</option><option value="all">All active bases</option>{activeBases.map((base) => <option key={base.id} value={base.id}>{base.name}</option>)}</Select><Button type="submit" disabled={queryText.trim().length < 2 || (!searchAllBases && !searchBaseId)}><Search size={16}/>Search</Button></form>
      {searchTerm && <div className="mt-5 space-y-3">{results.isPending ? <p className="text-sm text-slate-500">Searching…</p> : results.isError ? <p role="alert" className="text-sm text-red-700">Search could not be completed.</p> : results.data?.items.length ? results.data.items.map((result) => <article key={`${result.document_id}-${result.chunk_index}`} className="rounded-xl border border-slate-200 p-4"><p className="text-xs font-semibold text-blue-700">{result.knowledge_base_name} · {result.document_name} · section {result.chunk_index + 1}</p><p className="mt-2 text-sm leading-6 text-slate-700">{result.excerpt}</p></article>) : <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No matching passages in ready documents from active knowledge bases.</p>}</div>}
    </PanelBody></Panel>
    <Panel><PanelHeader title={activeBases.find((base) => base.id === effectiveBaseId)?.name ?? "Your documents"} description={documents.isError ? "Documents unavailable" : documents.isPending ? "Loading documents" : `${documentRange} documents`} action={<BookOpen size={17} className="text-slate-400"/>}/><PanelBody className="p-0">
      {canManage && activeBases.length > 1 && <p className="px-5 pt-4 text-xs text-slate-500">Move ready or failed documents between active bases. Source files, chunks, and ingestion history are retained.</p>}
      {documents.isPending && <div className="space-y-3 p-5">{[1,2,3].map((n) => <div key={n} className="h-16 animate-pulse rounded-lg bg-slate-100"/>)}</div>}
      {documents.isError && <div role="alert" className="p-5 text-sm text-red-700">Documents could not be loaded. <button className="font-semibold underline" onClick={() => documents.refetch()}>Retry</button></div>}
      {documents.data?.items.length === 0 && <div className="p-10 text-center"><FileText className="mx-auto text-slate-300"/><p className="mt-3 font-semibold">No documents yet</p><p className="mt-1 text-sm text-slate-500">Upload a PDF, text file, or Markdown guide to get started.</p></div>}
      <ul className="divide-y divide-slate-100">{documents.data?.items.map((item) => <DocumentRow key={item.id} item={item} bases={activeBases} canManage={canManage} busy={reprocess.isPending || remove.isPending || move.isPending} onReprocess={() => reprocess.mutate(item.id)} onDelete={() => remove.mutate(item.id)} onMove={(knowledgeBaseId) => move.mutate({ documentId: item.id, knowledgeBaseId })}/>)}</ul>
      {documents.data && documents.data.total > 0 && <nav aria-label="Document pages" className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-3"><p className="text-xs text-slate-500">Showing {documentRange} documents</p><div className="flex gap-2"><Button type="button" size="sm" variant="secondary" disabled={documents.isPending || documentOffset === 0} onClick={() => setDocumentPage({ baseId: effectiveBaseId ?? "", offset: Math.max(0, documentOffset - KNOWLEDGE_DOCUMENT_PAGE_SIZE) })}><ChevronLeft size={15}/>Previous</Button><Button type="button" size="sm" variant="secondary" disabled={documents.isPending || documentOffset + documents.data.items.length >= documents.data.total} onClick={() => setDocumentPage({ baseId: effectiveBaseId ?? "", offset: documentOffset + KNOWLEDGE_DOCUMENT_PAGE_SIZE })}>Next<ChevronRight size={15}/></Button></div></nav>}
    </PanelBody></Panel>
  </div>;
}

function DocumentRow({ item, bases, canManage, busy, onReprocess, onDelete, onMove }: { item: KnowledgeDocument; bases: { id: string; name: string }[]; canManage: boolean; busy: boolean; onReprocess: () => void; onDelete: () => void; onMove: (knowledgeBaseId: string) => void }) {
  const [targetBaseId, setTargetBaseId] = useState("");
  const latestJob = item.jobs[0];
  const needsReplacement = item.status === "failed" && latestJob?.requires_replacement;
  const statusVariant = item.status === "ready" ? "secondary" : item.status === "failed" ? "destructive" : "outline";
  const destinations = bases.filter((base) => base.id !== item.knowledge_base_id);
  return <li className="flex flex-wrap items-center gap-3 px-5 py-4"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-500"><FileText size={18}/></span><div className="min-w-0 flex-1"><Link href={`/dashboard/knowledge/${item.id}`} className="truncate text-sm font-semibold text-blue-800 hover:underline">{item.name}</Link><p className="mt-1 text-xs text-slate-500">{formatBytes(item.size_bytes)} · added {formatDateTime(item.created_at)}</p>{latestJob?.status === "failed" && <p className="mt-1 text-xs text-red-700">{needsReplacement ? "Processing failed. Upload a corrected file." : "Processing failed. You can retry this file."}</p>}</div><Badge variant={statusVariant} className="capitalize">{item.status}</Badge>{canManage && <>{destinations.length > 0 && <div className="flex items-center gap-2"><Select aria-label={`Move ${item.name} to knowledge base`} value={targetBaseId} onChange={(event) => setTargetBaseId(event.target.value)} disabled={busy || item.status === "queued" || item.status === "processing"} className="min-h-9 max-w-40 px-2 text-xs"><option value="">Move to…</option>{destinations.map((base) => <option key={base.id} value={base.id}>{base.name}</option>)}</Select><Button type="button" variant="secondary" size="sm" disabled={busy || !targetBaseId || item.status === "queued" || item.status === "processing"} onClick={() => onMove(targetBaseId)}>Move</Button></div>}<Button variant="ghost" size="sm" aria-label={`Reprocess ${item.name}`} disabled={busy || needsReplacement || item.status === "processing" || item.status === "queued"} onClick={onReprocess}><RotateCw size={15}/></Button><Button variant="ghost" size="sm" aria-label={`Delete ${item.name}`} disabled={busy} onClick={onDelete}><Trash2 size={15}/></Button></>}{item.status === "processing" && <LoaderCircle aria-label="Processing" size={15} className="animate-spin text-blue-700"/>}</li>;
}

function knowledgeBaseAuditLabel(
  eventType: string,
  details: Record<string, unknown>,
  knowledgeBaseId: string,
): string {
  if (eventType === "created") return "Knowledge base created";
  if (eventType === "archived") return "Knowledge base archived";
  if (eventType === "restored") return "Knowledge base restored";
  if (eventType === "default_changed") {
    return details.is_default === true ? "Set as workspace default" : "No longer the workspace default";
  }
  if (eventType === "document_moved") {
    return details.to_knowledge_base_id === knowledgeBaseId
      ? "A document was moved into this base"
      : "A document was moved out of this base";
  }
  if (eventType === "document_uploaded") return "A document was added to this base";
  if (eventType === "document_reprocessed") return "Document processing was restarted";
  if (eventType === "document_deleted") return "A document was removed from AI retrieval";
  if (eventType === "updated") {
    const fields = Array.isArray(details.changed_fields)
      ? details.changed_fields.filter((field): field is string => typeof field === "string")
      : [];
    return fields.length > 0 ? `Updated ${fields.join(" and ")}` : "Knowledge base updated";
  }
  return "Knowledge base changed";
}

function KnowledgeBaseDetailsForm({
  base,
  busy,
  saved,
  onSave,
}: {
  base: { id: string; name: string; description: string | null };
  busy: boolean;
  saved: boolean;
  onSave: (values: { id: string; name: string; description: string | null }) => void;
}) {
  const [name, setName] = useState(base.name);
  const [description, setDescription] = useState(base.description ?? "");
  const isUnchanged = name.trim() === base.name && (description.trim() || null) === base.description;

  return <form className="grid gap-3 border-t border-slate-100 pt-4 md:grid-cols-2" onSubmit={(event) => {
    event.preventDefault();
    onSave({ id: base.id, name: name.trim(), description: description.trim() || null });
  }}>
    <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Knowledge base name</span><Input aria-label="Knowledge base name" value={name} maxLength={120} required onChange={(event) => setName(event.target.value)}/></label>
    <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Description</span><Input aria-label="Knowledge base description" value={description} maxLength={500} onChange={(event) => setDescription(event.target.value)} placeholder="What this library contains"/></label>
    <div className="md:col-span-2"><Button type="submit" variant="secondary" disabled={busy || !name.trim() || isUnchanged}>{busy ? <LoaderCircle size={15} className="animate-spin"/> : null}Save base details</Button>{saved && <span role="status" className="ml-3 text-sm text-emerald-700">Knowledge base updated.</span>}</div>
  </form>;
}

function formatBytes(value: number) { return value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`; }
