"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText } from "lucide-react";
import { Button } from "@/components/ui";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/utils";
import { getKnowledgeBase } from "../api/knowledge-base-api";
import { getKnowledgeDocument, getKnowledgeSourcePreview, isKnowledgeDocumentProcessing, KNOWLEDGE_PROCESSING_POLL_INTERVAL_MS } from "../api/knowledge-api";

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

  if (document.isPending) return <div className="h-64 animate-pulse rounded-xl bg-muted"/>;
  if (document.isError || !document.data) {
    return <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 p-5 text-sm text-destructive">
      {document.error instanceof Error ? document.error.message : "Document not found or unavailable."}
      {document.error instanceof ApiError && document.error.status === 401 && <Link className="ml-1 font-medium underline" href="/login">Sign in again</Link>}
      <Link className="ml-2 font-medium underline" href="/dashboard/knowledge">Back to documents</Link>
    </div>;
  }

  const item = document.data;
  return <div className="space-y-6 text-foreground">
    <Link href="/dashboard/knowledge" className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"><ArrowLeft size={16}/> Document library</Link>
    <header>
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-lg bg-primary/10 text-primary"><FileText size={20}/></span>
        <div><p className="text-sm font-medium capitalize text-primary">{item.deleted_at ? "Removed from library" : item.status} · {item.content_type}</p><h1 className="mt-1 text-2xl font-semibold tracking-tight">{item.name}</h1></div>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{(item.size_bytes / 1024).toFixed(1)} KB · added {formatDateTime(item.created_at)}{item.deleted_at && ` · removed ${formatDateTime(item.deleted_at)}`}</p>
      <p className="mt-2 text-sm text-muted-foreground">Knowledge base: {knowledgeBase.isPending ? "Loading…" : knowledgeBase.isError ? "Unavailable" : <span className="font-medium text-foreground">{knowledgeBase.data?.name ?? "Unknown base"}</span>}</p>
      {knowledgeBase.isError && <p role="alert" className="mt-2 text-sm text-destructive">Knowledge library details could not be loaded: {knowledgeBase.error instanceof Error ? knowledgeBase.error.message : "Please try again."}</p>}
    </header>
    {isKnowledgeDocumentProcessing(item) && <p role="status" className="rounded-lg border border-primary/20 bg-primary/5 p-4 text-sm">This page updates automatically while the document is queued or processing.</p>}
    {item.deleted_at && <p role="status" className="rounded-lg border border-warning/30 bg-warning/10 p-4 text-sm">The source file and searchable passages have been removed. This record remains available for ingestion audit history.</p>}
    {!item.deleted_at && ["text/plain", "text/markdown"].includes(item.content_type) && <Panel>
      <PanelHeader title="Original source preview" description="A bounded plain-text preview of the tenant-owned source file. Content is displayed as text and is not interpreted as HTML."/>
      <PanelBody>
        {sourcePreview.isPending ? <p role="status" className="text-sm text-muted-foreground">Loading source preview…</p> : sourcePreview.isError ? <div role="alert" className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm">
          {sourcePreview.error instanceof ApiError && sourcePreview.error.status === 410 ? "The original source artifact has been cleaned up; the document and ingestion history remain available." : sourcePreview.error instanceof Error ? sourcePreview.error.message : "The source preview could not be loaded."}
          {sourcePreview.error instanceof ApiError && sourcePreview.error.status !== 410 && <Button variant="unstyled" type="button" className="ml-2 font-medium underline" onClick={() => sourcePreview.refetch()}>Retry</Button>}
        </div> : sourcePreview.data && <>
          <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-border bg-muted p-4 text-sm leading-6 text-foreground">{sourcePreview.data.content}</pre>
          {sourcePreview.data.truncated && <p className="mt-2 text-xs text-muted-foreground">Preview limited to the first {Math.round(sourcePreview.data.max_bytes / 1024)} KB. The original source remains unchanged.</p>}
        </>}
      </PanelBody>
    </Panel>}
    {!item.deleted_at && item.content_type === "application/pdf" && <Panel>
      <PanelHeader title="Original PDF" description="The original file is retained for ingestion and reprocessing."/>
      <PanelBody><p className="text-sm text-muted-foreground">PDF source preview is not available here. Use the Knowledge Library search to inspect the passages extracted for this bot.</p><Link href="/dashboard/knowledge" className="mt-3 inline-flex font-medium text-primary hover:underline">Open source search →</Link></PanelBody>
    </Panel>}
    <Panel>
      <PanelHeader title="Processing history" description="Each ingestion attempt is retained for audit and troubleshooting."/>
      <PanelBody className="space-y-3">{item.jobs.length ? item.jobs.map((job) => <article key={job.id} className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-medium capitalize">{job.status}</p><p className="mt-1 text-xs text-muted-foreground">Attempt {job.attempt_count} of {job.max_attempts} · queued {formatDateTime(job.created_at)}</p>
          {job.correlation_id && <p className="mt-1 break-all text-xs text-muted-foreground">Support reference: <code className="select-all font-mono">{job.correlation_id}</code> · <Link href={{ pathname: "/dashboard/operations", query: { trace: job.correlation_id } }} className="font-medium text-primary hover:underline">View request trace</Link></p>}
        </div><span className="text-xs text-muted-foreground">{job.completed_at ? `completed ${formatDateTime(job.completed_at)}` : `next attempt ${formatDateTime(job.next_attempt_at)}`}</span></div>
        {job.last_error && <p className="mt-3 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">{job.last_error}</p>}
      </article>) : <p className="text-sm text-muted-foreground">No processing attempts recorded.</p>}</PanelBody>
    </Panel>
    {!item.deleted_at && item.status === "ready" && <Panel>
      <PanelHeader title="Source citations" description="Search this document in the knowledge library to inspect matching passages."/>
      <PanelBody><p className="text-sm text-muted-foreground">Indexed as searchable, tenant-scoped text chunks. Search results include a document citation and section number.</p><Link href="/dashboard/knowledge" className="mt-4 inline-flex font-medium text-primary hover:underline">Return to document search →</Link></PanelBody>
    </Panel>}
  </div>;
}
