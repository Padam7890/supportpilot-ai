"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getKnowledgeDocument, getKnowledgeSourcePreview, isKnowledgeDocumentProcessing, KNOWLEDGE_PROCESSING_POLL_INTERVAL_MS } from "../api/knowledge-api";
import { getKnowledgeBase } from "../api/knowledge-base-api";
import { formatDateTime } from "@/lib/utils";

export function KnowledgeDetail() {
  const { id } = useParams<{ id: string }>();
  const document = useQuery({
    queryKey: ["knowledge-document", id],
    queryFn: () => getKnowledgeDocument(id),
    refetchInterval: ({ state }) => state.data && isKnowledgeDocumentProcessing(state.data)
      ? KNOWLEDGE_PROCESSING_POLL_INTERVAL_MS
      : false,
    refetchIntervalInBackground: false,
  });
  const knowledgeBaseId = document.data?.knowledge_base_id;
  const knowledgeBase = useQuery({
    queryKey: ["knowledge-base", knowledgeBaseId],
    queryFn: () => getKnowledgeBase(knowledgeBaseId ?? ""),
    enabled: Boolean(knowledgeBaseId),
  });
  const sourcePreview = useQuery({
    queryKey: ["knowledge-source-preview", id],
    queryFn: () => getKnowledgeSourcePreview(id),
    enabled: Boolean(document.data && !document.data.deleted_at && ["text/plain", "text/markdown"].includes(document.data.content_type)),
    retry: false,
  });
  if (document.isPending) return <div className="h-64 animate-pulse rounded-2xl bg-white"/>;
  if (document.isError || !document.data) return <div role="alert" className="rounded-xl bg-red-50 p-5 text-sm text-red-700">Document not found or unavailable. <Link className="font-semibold underline" href="/dashboard/knowledge">Back to documents</Link></div>;
  const item = document.data;
  return <div className="space-y-6">
    <Link href="/dashboard/knowledge" className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900"><ArrowLeft size={16}/> Document library</Link>
    <header><div className="flex items-center gap-3"><span className="grid size-12 place-items-center rounded-2xl bg-blue-50 text-blue-700"><FileText size={22}/></span><div><p className="text-sm font-semibold capitalize text-blue-700">{item.deleted_at ? "Removed from library" : item.status} · {item.content_type}</p><h1 className="mt-1 text-3xl font-bold tracking-tight">{item.name}</h1></div></div><p className="mt-3 text-sm text-slate-500">{(item.size_bytes / 1024).toFixed(1)} KB · added {formatDateTime(item.created_at)}{item.deleted_at && ` · removed ${formatDateTime(item.deleted_at)}`}</p><p className="mt-2 text-sm text-slate-600">Knowledge base: {knowledgeBase.isPending ? <span className="text-slate-400">Loading…</span> : knowledgeBase.isError ? <span className="text-slate-500">Unavailable</span> : <span className="font-semibold text-slate-800">{knowledgeBase.data?.name ?? "Unknown base"}</span>}</p></header>
    {isKnowledgeDocumentProcessing(item) && <p role="status" className="rounded-xl bg-blue-50 p-4 text-sm text-blue-800">This page updates automatically while the document is queued or processing.</p>}
    {item.deleted_at && <p role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">The source file and searchable passages have been removed. This record remains available for ingestion audit history.</p>}
    {!item.deleted_at && ["text/plain", "text/markdown"].includes(item.content_type) && <Panel><PanelHeader title="Original source preview" description="A bounded plain-text preview of the tenant-owned source file. Content is displayed as text and is not interpreted as HTML."/><PanelBody>{sourcePreview.isPending ? <p role="status" className="text-sm text-slate-500">Loading source preview…</p> : sourcePreview.isError ? <div role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{sourcePreview.error instanceof ApiError && sourcePreview.error.status === 410 ? "The original source artifact has been cleaned up; the document and ingestion history remain available." : "The source preview could not be loaded."}{sourcePreview.error instanceof ApiError && sourcePreview.error.status !== 410 && <button type="button" className="ml-2 font-semibold underline" onClick={() => sourcePreview.refetch()}>Retry</button>}</div> : sourcePreview.data && <><pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">{sourcePreview.data.content}</pre>{sourcePreview.data.truncated && <p className="mt-2 text-xs text-slate-500">Preview limited to the first {Math.round(sourcePreview.data.max_bytes / 1024)} KB. The original document remains unchanged.</p>}</>}</PanelBody></Panel>}
    {!item.deleted_at && item.content_type === "application/pdf" && <Panel><PanelHeader title="Original PDF" description="The original file is retained for ingestion and reprocessing."/><PanelBody><p className="text-sm text-slate-600">PDF source preview is not available here. Use the Knowledge Library search to inspect the passages extracted for this bot.</p><Link href="/dashboard/knowledge" className="mt-3 inline-flex font-semibold text-blue-700 hover:underline">Open source search →</Link></PanelBody></Panel>}
    <Panel><PanelHeader title="Processing history" description="Each ingestion attempt is retained for audit and troubleshooting."/><PanelBody className="space-y-3">{item.jobs.length ? item.jobs.map((job) => <article key={job.id} className="rounded-xl border border-slate-200 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-semibold capitalize">{job.status}</p><p className="mt-1 text-xs text-slate-500">Attempt {job.attempt_count} of {job.max_attempts} · queued {formatDateTime(job.created_at)}</p>{job.correlation_id && <p className="mt-1 break-all text-xs text-slate-500">Support reference: <code className="select-all font-mono">{job.correlation_id}</code> · <Link href={{ pathname: "/dashboard/operations", query: { trace: job.correlation_id } }} className="font-medium text-blue-700 hover:underline">View request trace</Link></p>}</div><span className="text-xs text-slate-500">{job.completed_at ? `completed ${formatDateTime(job.completed_at)}` : `next attempt ${formatDateTime(job.next_attempt_at)}`}</span></div>{job.last_error && <p className="mt-3 rounded-lg bg-red-50 p-3 text-xs text-red-700">{job.last_error}</p>}</article>) : <p className="text-sm text-slate-500">No processing attempts recorded.</p>}</PanelBody></Panel>
    {!item.deleted_at && item.status === "ready" && <Panel><PanelHeader title="Source citations" description="Search this document in the knowledge library to inspect matching passages."/><PanelBody><p className="text-sm text-slate-600">Indexed as searchable, tenant-scoped text chunks. Search results include a document citation and section number.</p><Link href="/dashboard/knowledge" className="mt-4 inline-flex font-semibold text-blue-700 hover:underline">Return to document search →</Link></PanelBody></Panel>}
  </div>;
}
