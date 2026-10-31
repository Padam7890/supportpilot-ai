"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { BookOpen, FileText, LoaderCircle, RotateCw, Search, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/utils";
import { deleteKnowledgeDocument, knowledgeKeys, listKnowledgeDocuments, reprocessKnowledgeDocument, searchKnowledge, uploadKnowledgeDocument } from "../api/knowledge-api";
import type { KnowledgeDocument } from "../types/knowledge.types";

export function KnowledgeLibrary() {
  const client = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [queryText, setQueryText] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const documents = useQuery({
    queryKey: knowledgeKeys.documents,
    queryFn: listKnowledgeDocuments,
    refetchInterval: (query) => {
      const pending = query.state.data?.items.some((item) => ["queued", "processing"].includes(item.status));
      return pending && typeof document !== "undefined" && document.visibilityState === "visible" ? 3000 : false;
    },
    refetchIntervalInBackground: false,
  });
  const results = useQuery({ queryKey: knowledgeKeys.search(searchTerm), queryFn: () => searchKnowledge(searchTerm), enabled: searchTerm.length >= 2 });
  const upload = useMutation({ mutationFn: uploadKnowledgeDocument, onSuccess: async () => { if (fileInput.current) fileInput.current.value = ""; await client.invalidateQueries({ queryKey: knowledgeKeys.documents }); } });
  const reprocess = useMutation({ mutationFn: reprocessKnowledgeDocument, onSuccess: () => client.invalidateQueries({ queryKey: knowledgeKeys.documents }) });
  const remove = useMutation({ mutationFn: deleteKnowledgeDocument, onSuccess: () => client.invalidateQueries({ queryKey: knowledgeKeys.documents }) });
  const writeError = upload.error ?? reprocess.error ?? remove.error;

  useEffect(() => {
    const visibilityChanged = () => {
      if (document.visibilityState === "visible") void client.invalidateQueries({ queryKey: knowledgeKeys.documents });
    };
    document.addEventListener("visibilitychange", visibilityChanged);
    return () => document.removeEventListener("visibilitychange", visibilityChanged);
  }, [client]);

  return <div className="space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-semibold text-blue-700">Knowledge base</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Documents</h1><p className="mt-2 max-w-2xl text-sm text-slate-500">Add support policies and product guides. Processing runs in a durable background queue.</p></div><Button onClick={() => fileInput.current?.click()} disabled={upload.isPending}><Upload size={16}/>{upload.isPending ? "Uploading…" : "Upload document"}</Button><input ref={fileInput} type="file" accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" className="sr-only" aria-label="Choose a PDF, text, or Markdown document" onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }}/></header>
    {writeError && <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">{writeError.message}</p>}
    <Panel><PanelHeader title="Search your sources" description="Find exact passages from processed documents."/><PanelBody><form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); setSearchTerm(queryText.trim()); }}><Input aria-label="Search documents" placeholder="Search policies, procedures, product details…" value={queryText} onChange={(event) => setQueryText(event.target.value)}/><Button type="submit" disabled={queryText.trim().length < 2}><Search size={16}/>Search</Button></form>
      {searchTerm && <div className="mt-5 space-y-3">{results.isPending ? <p className="text-sm text-slate-500">Searching…</p> : results.isError ? <p role="alert" className="text-sm text-red-700">Search could not be completed.</p> : results.data?.items.length ? results.data.items.map((result) => <article key={`${result.document_id}-${result.chunk_index}`} className="rounded-xl border border-slate-200 p-4"><p className="text-xs font-semibold text-blue-700">{result.document_name} · section {result.chunk_index + 1}</p><p className="mt-2 text-sm leading-6 text-slate-700">{result.excerpt}</p></article>) : <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No matching passages. Only ready documents appear in search.</p>}</div>}
    </PanelBody></Panel>
    <Panel><PanelHeader title="Your documents" description={`${documents.data?.total ?? 0} documents`} action={<BookOpen size={17} className="text-slate-400"/>}/><PanelBody className="p-0">
      {documents.isPending && <div className="space-y-3 p-5">{[1,2,3].map((n) => <div key={n} className="h-16 animate-pulse rounded-lg bg-slate-100"/>)}</div>}
      {documents.isError && <div role="alert" className="p-5 text-sm text-red-700">Documents could not be loaded. <button className="font-semibold underline" onClick={() => documents.refetch()}>Retry</button></div>}
      {documents.data?.items.length === 0 && <div className="p-10 text-center"><FileText className="mx-auto text-slate-300"/><p className="mt-3 font-semibold">No documents yet</p><p className="mt-1 text-sm text-slate-500">Upload a PDF, text file, or Markdown guide to get started.</p></div>}
      <ul className="divide-y divide-slate-100">{documents.data?.items.map((item) => <DocumentRow key={item.id} item={item} busy={reprocess.isPending || remove.isPending} onReprocess={() => reprocess.mutate(item.id)} onDelete={() => remove.mutate(item.id)}/>)}</ul>
    </PanelBody></Panel>
  </div>;
}

function DocumentRow({ item, busy, onReprocess, onDelete }: { item: KnowledgeDocument; busy: boolean; onReprocess: () => void; onDelete: () => void }) {
  const latestJob = item.jobs[0];
  const statusColor = item.status === "ready" ? "bg-emerald-50 text-emerald-700" : item.status === "failed" ? "bg-red-50 text-red-700" : "bg-blue-50 text-blue-700";
  return <li className="flex flex-wrap items-center gap-3 px-5 py-4"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-500"><FileText size={18}/></span><div className="min-w-0 flex-1"><Link href={`/dashboard/knowledge/${item.id}`} className="truncate text-sm font-semibold text-blue-800 hover:underline">{item.name}</Link><p className="mt-1 text-xs text-slate-500">{formatBytes(item.size_bytes)} · added {formatDateTime(item.created_at)}</p>{latestJob?.status === "failed" && <p className="mt-1 text-xs text-red-700">Processing failed. Retry the source file.</p>}</div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${statusColor}`}>{item.status}</span><Button variant="ghost" size="sm" aria-label={`Reprocess ${item.name}`} disabled={busy || item.status === "processing"} onClick={onReprocess}><RotateCw size={15}/></Button><Button variant="ghost" size="sm" aria-label={`Delete ${item.name}`} disabled={busy} onClick={onDelete}><Trash2 size={15}/></Button>{item.status === "processing" && <LoaderCircle aria-label="Processing" size={15} className="animate-spin text-blue-700"/>}</li>;
}

function formatBytes(value: number) { return value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`; }
