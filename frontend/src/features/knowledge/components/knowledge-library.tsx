"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Check, ChevronDown, ChevronLeft, ChevronRight, Clock3, FileText, FolderOpen, History, LoaderCircle, MoreHorizontal, Plus, RotateCw, Search, Star, Trash2, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { StatusAlert } from "@/components/ui/status-alert";
import { ApiError } from "@/lib/api/errors";
import { currentUserQueryKey, getCurrentUser } from "@/features/auth/api/auth-api";
import { aiAgentsKey, listAIAgents } from "@/features/ai/api/ai-agent-api";
import { formatDateTime } from "@/lib/utils";
import { archiveKnowledgeBase, createKnowledgeBase, knowledgeBaseKey, listKnowledgeBaseAudit, listKnowledgeBases, makeDefaultKnowledgeBase, restoreKnowledgeBase, updateKnowledgeBase } from "../api/knowledge-base-api";
import { deleteKnowledgeDocument, isKnowledgeDocumentProcessing, KNOWLEDGE_PROCESSING_POLL_INTERVAL_MS, knowledgeKeys, listKnowledgeDocuments, moveKnowledgeDocument, KNOWLEDGE_DOCUMENT_PAGE_SIZE, reprocessKnowledgeDocument, searchKnowledge, uploadKnowledgeDocument } from "../api/knowledge-api";
import type { KnowledgeDocument } from "../types/knowledge.types";

type UploadEntry = { file: File; status: "queued" | "uploading" | "processing" | "ready" | "failed"; error?: string };

export function KnowledgeLibrary() {
  const client = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [selectedBaseId, setSelectedBaseId] = useState<string>();
  const [historyBaseId, setHistoryBaseId] = useState<string>();
  const [historyOffset, setHistoryOffset] = useState(0);
  const [documentOffset, setDocumentOffset] = useState(0);
  const [archiveBaseId, setArchiveBaseId] = useState<string>();
  const [newBaseName, setNewBaseName] = useState("");
  const [newBaseOpen, setNewBaseOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadBaseId, setUploadBaseId] = useState("");
  const [uploadEntries, setUploadEntries] = useState<UploadEntry[]>([]);
  const [uploadSelectionError, setUploadSelectionError] = useState("");
  const [searchText, setSearchText] = useState("");
  const [searchTerm, setSearchTerm] = useState("");

  const user = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const canManage = ["owner", "admin"].includes(user.data?.role ?? "");
  const bases = useQuery({ queryKey: knowledgeBaseKey, queryFn: listKnowledgeBases });
  const agents = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents });
  const activeBases = bases.data?.items.filter((base) => base.status === "active") ?? [];
  const archivedBases = bases.data?.items.filter((base) => base.status === "archived") ?? [];
  const effectiveBaseId = (activeBases.some((base) => base.id === selectedBaseId) ? selectedBaseId : undefined)
    ?? activeBases.find((base) => base.is_default)?.id ?? activeBases[0]?.id;
  const selectedBase = activeBases.find((base) => base.id === effectiveBaseId);
  const historyBase = bases.data?.items.find((base) => base.id === historyBaseId) ?? selectedBase;
  const documents = useQuery({
    queryKey: [...knowledgeKeys.documents, effectiveBaseId, documentOffset],
    queryFn: () => listKnowledgeDocuments(effectiveBaseId, documentOffset),
    enabled: bases.isSuccess && Boolean(effectiveBaseId),
    refetchInterval: (query) => query.state.data?.items.some(isKnowledgeDocumentProcessing) ? KNOWLEDGE_PROCESSING_POLL_INTERVAL_MS : false,
    refetchIntervalInBackground: false,
  });
  const history = useQuery({
    queryKey: ["knowledge-base-audit", historyBase?.id, historyOffset],
    queryFn: () => listKnowledgeBaseAudit(historyBase?.id ?? "", historyOffset),
    enabled: canManage && Boolean(historyBase?.id),
  });
  const search = useQuery({
    queryKey: [...knowledgeKeys.search(searchTerm), effectiveBaseId],
    queryFn: () => searchKnowledge(searchTerm, effectiveBaseId),
    enabled: searchTerm.length >= 2 && Boolean(effectiveBaseId),
  });

  const uploadOne = useMutation({
    mutationFn: uploadKnowledgeDocument,
    onSuccess: async () => {
      await Promise.all([client.invalidateQueries({ queryKey: knowledgeKeys.documents }), client.invalidateQueries({ queryKey: knowledgeBaseKey })]);
    },
  });
  const createBase = useMutation({ mutationFn: () => createKnowledgeBase({ name: newBaseName.trim(), description: null }), onSuccess: async (base) => {
    setNewBaseName(""); setNewBaseOpen(false); setSelectedBaseId(base.id); setHistoryBaseId(base.id); setHistoryOffset(0);
    await client.invalidateQueries({ queryKey: knowledgeBaseKey });
  } });
  const updateBase = useMutation({ mutationFn: ({ id, name, description }: { id: string; name: string; description: string | null }) => updateKnowledgeBase(id, { name, description }), onSuccess: () => client.invalidateQueries({ queryKey: knowledgeBaseKey }) });
  const setDefault = useMutation({ mutationFn: makeDefaultKnowledgeBase, onSuccess: () => client.invalidateQueries({ queryKey: knowledgeBaseKey }) });
  const archive = useMutation({ mutationFn: archiveKnowledgeBase, onSuccess: async (_, baseId) => { setArchiveBaseId(undefined); setSelectedBaseId(undefined); setHistoryBaseId(baseId); await client.invalidateQueries({ queryKey: knowledgeBaseKey }); } });
  const restore = useMutation({ mutationFn: restoreKnowledgeBase, onSuccess: async (base) => { setSelectedBaseId(base.id); setHistoryBaseId(base.id); await client.invalidateQueries({ queryKey: knowledgeBaseKey }); } });
  const reprocess = useMutation({ mutationFn: reprocessKnowledgeDocument, onSuccess: () => client.invalidateQueries({ queryKey: knowledgeKeys.documents }) });
  const remove = useMutation({ mutationFn: deleteKnowledgeDocument, onSuccess: () => client.invalidateQueries({ queryKey: knowledgeKeys.documents }) });
  const move = useMutation({ mutationFn: ({ id, baseId }: { id: string; baseId: string }) => moveKnowledgeDocument(id, baseId), onSuccess: () => Promise.all([client.invalidateQueries({ queryKey: knowledgeKeys.documents }), client.invalidateQueries({ queryKey: knowledgeBaseKey })]) });

  useEffect(() => {
    if (documents.isSuccess && documentOffset > 0 && documents.data.items.length === 0 && documents.data.total <= documentOffset) setDocumentOffset(Math.max(0, documentOffset - KNOWLEDGE_DOCUMENT_PAGE_SIZE));
  }, [documents.data, documents.isSuccess, documentOffset]);

  const enqueueFiles = (files: FileList | null) => {
    if (!files?.length) return;
    const candidates = Array.from(files);
    const allowed = candidates.filter((file) => /\.(pdf|txt|md)$/i.test(file.name) && file.size <= 20 * 1024 * 1024);
    if (allowed.length !== candidates.length) setUploadSelectionError("Only PDF, TXT, and Markdown files up to 20 MB are supported.");
    else setUploadSelectionError("");
    setUploadEntries((current) => [...current, ...allowed.map((file) => ({ file, status: "queued" as const }))]);
  };
  const uploadQueued = async () => {
    if (!uploadBaseId) return;
    for (const [index, entry] of uploadEntries.entries()) {
      if (entry.status !== "queued" && entry.status !== "failed") continue;
      setUploadEntries((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: "uploading", error: undefined } : item));
      try {
        const uploaded = await uploadOne.mutateAsync({ file: entry.file, knowledgeBaseId: uploadBaseId });
        const status = uploaded.status === "ready" ? "ready" : uploaded.status === "failed" ? "failed" : "processing";
        setUploadEntries((current) => current.map((item) => item.file === entry.file ? { ...item, status, error: status === "failed" ? uploaded.jobs[0]?.last_error ?? "Processing failed" : undefined } : item));
      } catch (error) {
        setUploadEntries((current) => current.map((item) => item.file === entry.file ? { ...item, status: "failed", error: error instanceof Error ? error.message : "Upload failed" } : item));
      }
    }
    setSelectedBaseId(uploadBaseId);
    setDocumentOffset(0);
    await client.invalidateQueries({ queryKey: knowledgeKeys.documents });
  };
  const writeError = createBase.error ?? updateBase.error ?? setDefault.error ?? archive.error ?? restore.error ?? move.error ?? reprocess.error ?? remove.error;
  const documentRange = documents.data ? documents.data.items.length ? `${documentOffset + 1}–${documentOffset + documents.data.items.length} of ${documents.data.total}` : `0 of ${documents.data.total}` : "Loading documents";
  const historyPageLimit = history.data?.limit ?? 10;
  const baseToArchive = activeBases.find((base) => base.id === archiveBaseId);

  return <div className="space-y-6 text-foreground">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="text-2xl font-semibold tracking-tight">Knowledge bases</h1><p className="mt-1.5 text-sm text-muted-foreground">Organize support documents and assign them to your AI bots.</p></div>
        <div className="flex items-center gap-2">
          {canManage && <Link href="/dashboard/knowledge/articles/new" className="inline-flex h-10 items-center gap-2 rounded-lg border border-border px-4 text-sm font-medium text-foreground transition-colors hover:bg-accent">Write article</Link>}
          {canManage && <Button onClick={() => { setUploadBaseId(effectiveBaseId ?? ""); setUploadEntries([]); setUploadSelectionError(""); setUploadOpen(true); }} disabled={!activeBases.length} className="h-10 rounded-lg bg-primary px-4 text-primary-foreground hover:bg-primary-hover"><Upload size={15}/>Upload</Button>}
        </div>
      </header>
      {writeError && <StatusAlert tone="error">{writeError.message}</StatusAlert>}
      {!user.isPending && user.data && !canManage && <div className="rounded-lg border border-border bg-muted px-4 py-3 text-sm text-muted-foreground">Your role has read-only access to knowledge settings.</div>}

      <section className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
          <div className="flex flex-wrap items-center gap-1" role="tablist" aria-label="Knowledge bases">
            {activeBases.map((base) => <button key={base.id} role="tab" aria-selected={effectiveBaseId === base.id} onClick={() => { setSelectedBaseId(base.id); setHistoryBaseId(base.id); setDocumentOffset(0); setHistoryOffset(0); setSearchTerm(""); }} className={`rounded-full px-3.5 py-2 text-sm transition-colors ${effectiveBaseId === base.id ? "bg-accent text-foreground ring-1 ring-primary/30" : "text-muted-foreground hover:bg-accent hover:text-foreground"}`}>{base.name}{base.is_default && <span className="ml-1.5 text-xs text-muted-foreground">Default</span>}</button>)}
            {canManage && <button onClick={() => setNewBaseOpen((open) => !open)} className="inline-flex items-center gap-1 rounded-full px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"><Plus size={14}/>New</button>}
          </div>
          {selectedBase && <div className="flex items-center gap-2 text-xs text-muted-foreground"><span>{selectedBase.ready_document_count} ready</span><span className="text-border">·</span><span>{selectedBase.document_count} documents</span><button aria-label="Knowledge base history" title="View recent changes" onClick={() => document.getElementById("knowledge-history")?.scrollIntoView({ behavior: "smooth" })} className="ml-1 rounded-md p-1.5 hover:bg-accent hover:text-foreground"><History size={15}/></button><button aria-label="Knowledge base options" title="Knowledge base options" onClick={() => setNewBaseOpen((open) => !open)} className="rounded-md p-1.5 hover:bg-accent hover:text-foreground"><MoreHorizontal size={16}/></button></div>}
        </div>
        {newBaseOpen && canManage && <form className="flex max-w-xl gap-2" onSubmit={(event) => { event.preventDefault(); if (newBaseName.trim()) createBase.mutate(); }}><Input autoFocus aria-label="Knowledge base name" placeholder="Name this knowledge base" value={newBaseName} onChange={(event) => setNewBaseName(event.target.value)} className="border-border bg-background text-foreground placeholder:text-muted-foreground"/><Button type="submit" disabled={!newBaseName.trim() || createBase.isPending} className="bg-primary text-primary-foreground hover:bg-primary-hover">Create base</Button><Button type="button" variant="ghost" onClick={() => setNewBaseOpen(false)} className="text-muted-foreground hover:bg-accent">Cancel</Button></form>}

        {bases.isPending && <p role="status" className="py-10 text-sm text-muted-foreground">Loading knowledge bases…</p>}
        {bases.isError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">Knowledge bases could not be loaded: {errorMessage(bases.error)} {bases.error instanceof ApiError && bases.error.status === 401 && <Link href="/login" className="underline">Sign in again</Link>} <button onClick={() => bases.refetch()} className="ml-1 underline">Retry</button></div>}
        {!bases.isPending && !bases.isError && !activeBases.length && <div className="rounded-xl border border-dashed border-border px-6 py-14 text-center"><FolderOpen className="mx-auto size-7 text-muted-foreground"/><p className="mt-3 font-medium">No active knowledge base</p><p className="mt-1 text-sm text-muted-foreground">Create a base to start adding sources for your AI bots.</p></div>}
        {selectedBase && <>
          <section className="flex flex-wrap items-start justify-between gap-3">
            <div><h2 className="text-lg font-semibold">{selectedBase.name}</h2><p className="mt-1 text-sm text-muted-foreground">{selectedBase.description || "Add a description"}</p><p className="mt-2 text-xs text-muted-foreground">{selectedBase.is_default ? "Default library" : "Knowledge library"} · Used by {agents.data?.items.filter((agent) => agent.status === "active" && (agent.knowledge_base_ids ?? []).includes(selectedBase.id)).map((agent) => agent.name).join(", ") || "no active bots"}</p></div>
            {canManage && <div className="flex gap-1">
              {!selectedBase.is_default && <button title="Make default" aria-label="Make this base the default" onClick={() => setDefault.mutate(selectedBase.id)} disabled={setDefault.isPending} className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"><Star size={16}/></button>}
              {!selectedBase.is_default && <button title="Archive base" aria-label="Archive knowledge base" onClick={() => setArchiveBaseId(selectedBase.id)} className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"><Archive size={16}/></button>}
            </div>}
          </section>
          {canManage && <BaseDetailsInline key={selectedBase.id} base={selectedBase} busy={updateBase.isPending} onSave={(values) => updateBase.mutate(values)}/>}

          <section className="overflow-hidden rounded-xl border border-border bg-card">
            <div className="border-b border-border p-4">
              <form className="relative" onSubmit={(event) => { event.preventDefault(); setSearchTerm(searchText.trim()); }}>
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"/><Input aria-label="Search documents" placeholder="Search policies, procedures, product details…" value={searchText} onChange={(event) => setSearchText(event.target.value)} className="h-10 border-border bg-muted pl-10 text-foreground placeholder:text-muted-foreground"/>
                {searchText && <button type="button" aria-label="Clear search" onClick={() => { setSearchText(""); setSearchTerm(""); }} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-accent"><X size={14}/></button>}
              </form>
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)_90px_165px_90px_100px] gap-3 border-b border-border px-5 py-3 text-xs font-medium text-muted-foreground max-md:grid-cols-[minmax(0,1fr)_74px_90px]">
              <span>Name</span><span className="max-md:hidden">Size</span><span className="max-md:hidden">Added</span><span>Status</span><span className="text-right">Actions</span>
            </div>
            {searchTerm ? <div className="divide-y divide-border">{search.isPending ? <p className="p-5 text-sm text-muted-foreground">Searching…</p> : search.isError ? <p role="alert" className="p-5 text-sm text-destructive">Search failed: {errorMessage(search.error)}</p> : search.data?.items.length ? search.data.items.map((result) => <article key={`${result.document_id}-${result.chunk_index}`} className="px-5 py-4"><p className="text-xs text-primary">{result.document_name} · section {result.chunk_index + 1}</p><p className="mt-2 text-sm leading-6 text-foreground">{result.excerpt}</p></article>) : <p className="p-6 text-sm text-muted-foreground">No matching passages in ready documents.</p>}</div>
              : documents.isPending ? <div className="space-y-3 p-5"><div className="h-12 animate-pulse rounded bg-muted"/><div className="h-12 animate-pulse rounded bg-muted"/></div>
              : documents.isError ? <p role="alert" className="p-5 text-sm text-destructive">Documents could not be loaded: {errorMessage(documents.error)} {documents.error instanceof ApiError && documents.error.status === 401 && <Link href="/login" className="underline">Sign in again</Link>} <button className="underline" onClick={() => documents.refetch()}>Retry</button></p>
              : documents.data?.items.length ? <ul className="divide-y divide-border">{documents.data.items.map((item) => <DocumentRow key={item.id} item={item} bases={activeBases} canManage={canManage} busy={reprocess.isPending || remove.isPending || move.isPending} onReprocess={() => reprocess.mutate(item.id)} onDelete={() => remove.mutate(item.id)} onMove={(baseId) => move.mutate({ id: item.id, baseId })}/>)}</ul>
              : <div className="px-5 py-14 text-center"><FileText className="mx-auto size-6 text-muted-foreground"/><p className="mt-3 text-sm font-medium">This base is empty</p><p className="mt-1 text-sm text-muted-foreground">Upload a document or write an article to give your AI bots trusted answers.</p>{canManage && <div className="mt-4 flex justify-center gap-2"><Link href="/dashboard/knowledge/articles/new" className="inline-flex h-9 items-center rounded-lg border border-border px-3 text-sm hover:bg-accent">Write article</Link><Button onClick={() => { setUploadBaseId(selectedBase.id); setUploadEntries([]); setUploadOpen(true); }} className="h-9 bg-primary text-primary-foreground hover:bg-primary-hover"><Upload size={14}/>Upload document</Button></div>}</div>}
            {!searchTerm && documents.data && documents.data.total > 0 && <div className="flex items-center justify-between border-t border-border px-5 py-3 text-xs text-muted-foreground"><span>{documentRange} documents</span><div className="flex gap-1"><button aria-label="Previous page" disabled={documentOffset === 0 || documents.isPending} onClick={() => setDocumentOffset(Math.max(0, documentOffset - KNOWLEDGE_DOCUMENT_PAGE_SIZE))} className="rounded-md p-1.5 hover:bg-accent disabled:opacity-40"><ChevronLeft size={16}/></button><button aria-label="Next page" disabled={documents.isPending || documentOffset + (documents.data?.items.length ?? 0) >= (documents.data?.total ?? 0)} onClick={() => setDocumentOffset(documentOffset + KNOWLEDGE_DOCUMENT_PAGE_SIZE)} className="rounded-md p-1.5 hover:bg-accent disabled:opacity-40"><ChevronRight size={16}/></button></div></div>}
          </section>
        </>}

        {archivedBases.length > 0 && <section className="space-y-2 border-t border-border pt-4"><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Archived libraries</h3>{archivedBases.map((base) => <div key={base.id} className="flex items-center justify-between rounded-lg border border-border px-4 py-3"><div><p className="text-sm font-medium">{base.name}</p><p className="mt-0.5 text-xs text-muted-foreground">{base.document_count} preserved documents</p></div><div className="flex gap-2"><Button variant="ghost" size="sm" onClick={() => { setHistoryBaseId(base.id); setHistoryOffset(0); document.getElementById("knowledge-history")?.scrollIntoView({ behavior: "smooth" }); }} className="text-muted-foreground hover:bg-accent">View history</Button><Button variant="outline" size="sm" onClick={() => restore.mutate(base.id)} disabled={restore.isPending} className="border-border bg-transparent text-foreground hover:bg-accent">Restore</Button></div></div>)}</section>}
        {canManage && historyBase && <section id="knowledge-history" className="border-t border-border pt-4"><details><summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium text-muted-foreground"><span className="inline-flex items-center gap-2"><Clock3 size={15}/>Recent changes · {historyBase.name}</span><ChevronDown size={15}/></summary><div className="mt-3 space-y-2">{history.isPending ? <p className="text-xs text-muted-foreground">Loading history…</p> : history.isError ? <p role="alert" className="text-xs text-destructive">History could not be loaded: {errorMessage(history.error)} <button onClick={() => history.refetch()} className="underline">Retry</button></p> : history.data?.items.length ? history.data.items.map((event) => <div key={event.id} className="flex justify-between gap-3 rounded-lg border border-border px-3 py-2.5 text-xs"><span className="text-foreground">{auditLabel(event.event_type, event.details)}<span className="ml-2 text-muted-foreground">{event.actor_name}</span></span><time className="shrink-0 text-muted-foreground">{formatDateTime(event.created_at)}</time></div>) : <p className="text-xs text-muted-foreground">No changes recorded yet.</p>}{history.data && history.data.total > history.data.limit && <div className="flex items-center justify-between pt-1 text-xs text-muted-foreground"><span>{historyOffset + 1}–{Math.min(historyOffset + history.data.items.length, history.data.total)} of {history.data.total}</span><div className="flex gap-1"><button disabled={historyOffset === 0} onClick={() => setHistoryOffset(Math.max(0, historyOffset - historyPageLimit))} className="rounded p-1 hover:bg-accent disabled:opacity-40" aria-label="Newer changes"><ChevronLeft size={15}/></button><button disabled={historyOffset + history.data.items.length >= history.data.total} onClick={() => setHistoryOffset(historyOffset + historyPageLimit)} className="rounded p-1 hover:bg-accent disabled:opacity-40" aria-label="Older changes"><ChevronRight size={15}/></button></div></div>}</div></details></section>}
      </section>

    <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
      <DialogContent className="!fixed !inset-y-0 !right-0 !left-auto !top-0 !h-dvh !w-[min(720px,100vw)] !max-w-none !translate-x-0 !translate-y-0 !gap-0 !overflow-hidden !rounded-none !border-l !border-border !bg-background !p-0 !text-foreground data-open:!animate-in data-open:!slide-in-from-right data-closed:!slide-out-to-right">
        <div className="flex h-full min-h-0 flex-col">
          <DialogHeader className="border-b border-border px-7 py-6 text-left"><DialogTitle className="text-2xl font-semibold">Upload documents</DialogTitle><DialogDescription className="text-muted-foreground">Files are processed so your AI bots can search them.</DialogDescription></DialogHeader>
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-7 py-6">
            <label className="block space-y-2 text-sm font-medium"><span className="text-muted-foreground">Add to library</span><Select aria-label="Choose knowledge base" value={uploadBaseId} onChange={(event) => setUploadBaseId(event.target.value)} className="h-12 border-border bg-background text-base text-foreground">{activeBases.map((base) => <option key={base.id} value={base.id}>{base.name}{base.is_default ? " (default)" : ""}</option>)}</Select></label>
            <button type="button" onClick={() => fileInput.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); enqueueFiles(event.dataTransfer.files); }} className="flex min-h-48 w-full flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-muted px-5 text-center transition-colors hover:border-primary hover:bg-accent"><Upload className="size-8 text-primary"/><span className="mt-4 text-lg font-medium">Drag files here or <span className="text-primary">browse</span></span><span className="mt-1 text-sm text-muted-foreground">PDF, TXT, MD · up to 20 MB each</span></button>
            <input ref={fileInput} type="file" multiple accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" className="sr-only" aria-label="Choose documents to upload" onChange={(event) => { enqueueFiles(event.target.files); event.currentTarget.value = ""; }}/>
            {uploadSelectionError && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{uploadSelectionError}</p>}
            {uploadEntries.length > 0 && <div className="divide-y divide-border">{uploadEntries.map((entry, index) => <div key={`${entry.file.name}-${entry.file.lastModified}-${index}`} className="flex items-center gap-3 py-4"><FileText className="size-5 shrink-0 text-muted-foreground"/><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{entry.file.name}</p><p className={`mt-1 text-sm ${entry.status === "failed" ? "text-destructive" : "text-muted-foreground"}`}>{entry.status === "queued" ? formatBytes(entry.file.size) : entry.status === "uploading" ? "Uploading…" : entry.status === "processing" ? "Queued for processing" : entry.status === "ready" ? "Ready for AI search" : entry.error || "Could not upload file"}</p>{entry.status === "uploading" && <div className="mt-2 h-1 rounded-full bg-muted"><div className="h-full w-2/3 animate-pulse rounded-full bg-primary"/></div>}</div>{(entry.status === "processing" || entry.status === "ready") ? <span className={`inline-flex items-center gap-1.5 text-sm ${entry.status === "ready" ? "text-success" : "text-muted-foreground"}`}>{entry.status === "ready" ? <Check size={16}/> : <LoaderCircle size={15} className="animate-spin"/>}{entry.status === "ready" ? "Ready" : "Added"}</span> : entry.status === "failed" ? <button onClick={() => setUploadEntries((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: "queued", error: undefined } : item))} className="rounded-lg border border-border px-3 py-2 text-sm hover:bg-accent">Retry</button> : <button aria-label={`Remove ${entry.file.name}`} disabled={entry.status === "uploading"} onClick={() => setUploadEntries((current) => current.filter((_, itemIndex) => itemIndex !== index))} className="rounded p-2 text-muted-foreground hover:bg-accent"><X size={16}/></button>}</div>)}</div>}
            {documents.data?.items.filter((item) => isKnowledgeDocumentProcessing(item)).map((item) => <div key={item.id} className="flex items-center gap-3 border-t border-border py-4"><LoaderCircle size={17} className="animate-spin text-primary"/><div><p className="text-sm font-medium">{item.name}</p><p className="text-sm text-muted-foreground">Processing…</p></div></div>)}
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-7 py-4"><Button variant="outline" onClick={() => setUploadOpen(false)} className="border-border bg-transparent text-foreground hover:bg-accent">Done</Button><Button onClick={uploadQueued} disabled={!uploadEntries.some((entry) => entry.status === "queued" || entry.status === "failed") || uploadOne.isPending} className="bg-primary text-primary-foreground hover:bg-primary-hover">{uploadOne.isPending ? <LoaderCircle size={15} className="animate-spin"/> : <Upload size={15}/>}Upload files</Button></div>
        </div>
      </DialogContent>
    </Dialog>
    {baseToArchive && <ConfirmDialog open onOpenChange={(open) => { if (!open && !archive.isPending) setArchiveBaseId(undefined); }} title={`Archive “${baseToArchive.name}”?`} description="Its documents and history are preserved, but retrieval stops using this library until it is restored." confirmLabel="Archive library" pendingLabel="Archiving…" confirmVariant="destructive" pending={archive.isPending} onConfirm={() => archive.mutate(baseToArchive.id)}/>}
  </div>;
}

function BaseDetailsInline({ base, busy, onSave }: { base: { id: string; name: string; description: string | null }; busy: boolean; onSave: (values: { id: string; name: string; description: string | null }) => void }) {
  const [name, setName] = useState(base.name);
  const [description, setDescription] = useState(base.description ?? "");
  const [editing, setEditing] = useState(false);
  if (!editing) return <button type="button" onClick={() => setEditing(true)} className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">Edit library details</button>;
  return <form className="grid gap-3 rounded-xl border border-border bg-card p-4 md:grid-cols-[1fr_1.3fr_auto]" onSubmit={(event) => { event.preventDefault(); onSave({ id: base.id, name: name.trim(), description: description.trim() || null }); setEditing(false); }}>
    <Input aria-label="Knowledge base name" value={name} onChange={(event) => setName(event.target.value)} className="border-border bg-muted text-foreground"/>
    <Input aria-label="Knowledge base description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Description" className="border-border bg-muted text-foreground placeholder:text-muted-foreground"/>
    <div className="flex gap-2"><Button type="submit" disabled={busy || !name.trim()} className="bg-primary text-primary-foreground hover:bg-primary-hover">Save</Button><Button type="button" variant="ghost" onClick={() => setEditing(false)} className="text-muted-foreground hover:bg-accent">Cancel</Button></div>
  </form>;
}

function DocumentRow({ item, bases, canManage, busy, onReprocess, onDelete, onMove }: { item: KnowledgeDocument; bases: { id: string; name: string }[]; canManage: boolean; busy: boolean; onReprocess: () => void; onDelete: () => void; onMove: (baseId: string) => void }) {
  const [targetBaseId, setTargetBaseId] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const job = item.jobs[0];
  const needsReplacement = item.status === "failed" && job?.requires_replacement;
  const statusTone = item.status === "ready" ? "text-success" : item.status === "failed" ? "text-destructive" : "text-warning";
  const destinations = bases.filter((base) => base.id !== item.knowledge_base_id);
  return <li className="grid grid-cols-[minmax(0,1fr)_90px_165px_90px_100px] items-center gap-3 px-5 py-4 transition-colors hover:bg-accent max-md:grid-cols-[minmax(0,1fr)_74px_90px]">
    <div className="flex min-w-0 items-center gap-3"><FileText className="size-4 shrink-0 text-muted-foreground"/><div className="min-w-0"><Link href={`/dashboard/knowledge/${item.id}`} className="block truncate text-sm font-medium text-foreground hover:text-primary">{item.name}</Link>{item.status === "failed" && <p className="mt-1 truncate text-xs text-destructive">{needsReplacement ? "Upload a corrected file to retry." : job?.last_error || "Processing failed. Retry this file."}</p>}</div></div>
    <span className="text-sm text-muted-foreground max-md:hidden">{formatBytes(item.size_bytes)}</span><span className="text-sm text-muted-foreground max-md:hidden">{formatDateTime(item.created_at)}</span><span className={`text-sm capitalize ${statusTone}`}>● {item.status === "queued" ? "Processing" : item.status}</span>
    <div className="flex justify-end gap-1">{canManage && destinations.length > 0 && <select aria-label={`Move ${item.name} to another library`} value={targetBaseId} onChange={(event) => { setTargetBaseId(event.target.value); if (event.target.value) onMove(event.target.value); }} disabled={busy || isKnowledgeDocumentProcessing(item)} className="max-w-[90px] rounded-md bg-transparent px-1 text-[11px] text-muted-foreground outline-none focus-visible:ring-1 focus-visible:ring-ring"><option value="">Move</option>{destinations.map((base) => <option key={base.id} value={base.id}>{base.name}</option>)}</select>}{canManage && <div className="relative"><button aria-label={`More actions for ${item.name}`} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)} className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"><MoreHorizontal size={16}/></button>{menuOpen && <div className="absolute right-0 top-full z-20 mt-1 min-w-36 rounded-lg border border-border bg-popover text-popover-foreground p-1 shadow-md"><button disabled={busy || needsReplacement || isKnowledgeDocumentProcessing(item)} onClick={() => { setMenuOpen(false); onReprocess(); }} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs hover:bg-accent disabled:opacity-40"><RotateCw size={13}/>Reprocess</button><button disabled={busy} onClick={() => { setMenuOpen(false); onDelete(); }} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-destructive hover:bg-accent disabled:opacity-40"><Trash2 size={13}/>Remove</button></div>}</div>}{isKnowledgeDocumentProcessing(item) && <LoaderCircle size={15} className="animate-spin text-primary"/>}</div>
  </li>;
}

function auditLabel(eventType: string, details: Record<string, unknown>) {
  if (eventType === "created") return "Knowledge base created";
  if (eventType === "archived") return "Knowledge base archived";
  if (eventType === "restored") return "Knowledge base restored";
  if (eventType === "default_changed") return details.is_default === true ? "Set as default library" : "Default library changed";
  if (eventType === "document_moved") return "A document was moved between libraries";
  if (eventType.startsWith("document_")) return `Document ${eventType.slice("document_".length).replaceAll("_", " ")}`;
  return "Knowledge base updated";
}

function formatBytes(value: number) { return value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`; }

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Please try again.";
}
