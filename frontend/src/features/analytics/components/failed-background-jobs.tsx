"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, LoaderCircle, RefreshCw, RotateCcw, Waypoints } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getFailedBackgroundJobs } from "@/features/analytics/api/analytics-api";
import { reprocessKnowledgeDocument, knowledgeKeys } from "@/features/knowledge/api/knowledge-api";
import { aiQueryKeys, retryAIExecution } from "@/features/ai/api/ai-api";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { retryCatalogSyncJob, shopifyQueryKeys } from "@/features/integrations/api/shopify-api";

const jobLabels: Record<string, string> = {
  ai_execution: "AI response",
  automation_execution: "Automation",
  catalog_sync: "Catalog sync",
  catalog_webhook: "Catalog event",
  document_ingestion: "Document processing",
  commerce_action: "Commerce action",
  outbound_delivery: "Message delivery",
};

export function FailedBackgroundJobs({ onTrace }: { onTrace?: (correlationId: string) => void }) {
  const queryClient = useQueryClient();
  const user = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const jobs = useQuery({
    queryKey: ["analytics", "background-failures", 20],
    queryFn: () => getFailedBackgroundJobs(20),
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 60_000 : false,
    refetchIntervalInBackground: false,
  });
  const retry = useMutation({
    mutationFn: ({ jobId, jobKind }: { jobId: string; jobKind: "ai_execution" | "catalog_sync" }) =>
      jobKind === "ai_execution" ? retryAIExecution(jobId) : retryCatalogSyncJob(jobId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["analytics", "background-failures"] }),
        queryClient.invalidateQueries({ queryKey: aiQueryKeys.history }),
        queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogJobs }),
        queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogStatus }),
      ]);
    },
  });
  const retryIngestion = useMutation({
    mutationFn: reprocessKnowledgeDocument,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["analytics", "background-failures"] }),
        queryClient.invalidateQueries({ queryKey: knowledgeKeys.documents }),
      ]);
    },
  });
  const role = user.data?.role ?? "";
  const canRetryAI = ["owner", "admin", "agent"].includes(role);
  const canRetryCatalog = ["owner", "admin"].includes(role);
  const canRetryIngestion = ["owner", "admin"].includes(role);

  function retryDocument(documentId: string | null | undefined) {
    if (documentId) retryIngestion.mutate(documentId);
  }

  return <section aria-labelledby="failed-jobs-title" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="text-xs font-bold uppercase tracking-[.14em] text-blue-700">Background processing</p>
        <h2 id="failed-jobs-title" className="mt-1 text-lg font-semibold text-slate-950">Failed jobs</h2>
        <p className="mt-1 text-sm text-slate-500">Recent terminal failures for this workspace. Sensitive job payloads are omitted.</p>
      </div>
      <Button variant="secondary" size="sm" onClick={() => void jobs.refetch()} disabled={jobs.isFetching} aria-label="Refresh failed jobs">
        <RefreshCw size={14} className={jobs.isFetching ? "animate-spin" : ""}/><span className="hidden sm:inline">Refresh</span>
      </Button>
    </header>

    {jobs.isPending ? <div role="status" className="mt-5 flex items-center gap-2 rounded-xl bg-slate-50 p-5 text-sm text-slate-500"><LoaderCircle size={16} className="animate-spin"/>Loading failed jobs…</div>
      : jobs.isError ? <div role="alert" className="mt-5 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><CircleAlert size={17} className="mt-0.5 shrink-0"/><span>Failed job history could not be loaded. Refresh to try again.</span></div>
      : jobs.data.items.length === 0 ? <p className="mt-5 rounded-xl border border-emerald-100 bg-emerald-50/60 p-4 text-sm text-emerald-900">No terminal background job failures are recorded for this workspace.</p>
      : <>
        <p className="mt-5 text-xs text-slate-500">{jobs.data.total_failed} failed job{jobs.data.total_failed === 1 ? "" : "s"} total · showing the latest {jobs.data.items.length}</p>
        <ul className="mt-3 divide-y divide-slate-100 rounded-xl border border-slate-200">
          {jobs.data.items.map((job) => <li key={`${job.job_kind}:${job.job_id}`} className="flex flex-wrap items-center justify-between gap-x-5 gap-y-2 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-900">{jobLabels[job.job_kind] ?? "Background job"}</p>
              <p className="mt-0.5 text-xs text-slate-500">{job.error_code ? `Code: ${job.error_code}` : "No public error code available"} · {job.attempts} attempt{job.attempts === 1 ? "" : "s"}{["ai_execution", "catalog_sync"].includes(job.job_kind) ? ` · ${job.manual_retry_count}/3 manual retries` : ""}</p>
            </div>
            <div className="flex items-center gap-3">
              <time className="text-xs tabular-nums text-slate-500" dateTime={job.failed_at}>{new Date(job.failed_at).toLocaleString()}</time>
              {job.correlation_id && onTrace && <Button size="sm" variant="ghost" onClick={() => { const correlationId = job.correlation_id; if (correlationId) onTrace(correlationId); }} aria-label="Trace related background jobs"><Waypoints size={14}/>Trace</Button>}
              {job.job_kind === "ai_execution" && canRetryAI && job.manual_retry_available && <Button size="sm" variant="secondary" disabled={retry.isPending} onClick={() => retry.mutate({ jobId: job.job_id, jobKind: "ai_execution" })}><RotateCcw size={14} className={retry.isPending && retry.variables?.jobId === job.job_id ? "animate-spin" : ""}/>{retry.isPending && retry.variables?.jobId === job.job_id ? "Queueing…" : "Retry AI"}</Button>}
              {job.job_kind === "catalog_sync" && canRetryCatalog && job.manual_retry_available && <Button size="sm" variant="secondary" disabled={retry.isPending} onClick={() => retry.mutate({ jobId: job.job_id, jobKind: "catalog_sync" })}><RotateCcw size={14} className={retry.isPending && retry.variables?.jobId === job.job_id ? "animate-spin" : ""}/>{retry.isPending && retry.variables?.jobId === job.job_id ? "Queueing…" : "Retry sync"}</Button>}
              {job.job_kind === "document_ingestion" && canRetryIngestion && job.document_id && <Button size="sm" variant="secondary" disabled={retryIngestion.isPending} onClick={() => retryDocument(job.document_id)}><RotateCcw size={14} className={retryIngestion.isPending && retryIngestion.variables === job.document_id ? "animate-spin" : ""}/>{retryIngestion.isPending && retryIngestion.variables === job.document_id ? "Queueing…" : "Retry processing"}</Button>}
            </div>
          </li>)}
        </ul>
        {retry.isError && <p role="alert" className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">The {retry.variables?.jobKind === "catalog_sync" ? "catalog sync" : "AI job"} could not be retried. Refresh the list and check the integration or conversation status.</p>}
        {retry.isSuccess && <p role="status" className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{retry.variables?.jobKind === "catalog_sync" ? "Catalog sync queued from the first page." : "AI execution queued for another attempt."}</p>}
        {retryIngestion.isError && <p role="alert" className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">Document processing could not be queued. Check that its source file is still available, then refresh.</p>}
        {retryIngestion.isSuccess && <p role="status" className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">Document processing queued. Its history is available in the Knowledge Library.</p>}
      </>}
  </section>;
}
