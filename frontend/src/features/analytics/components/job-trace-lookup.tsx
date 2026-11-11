"use client";

import { useMutation } from "@tanstack/react-query";
import { RefreshCw, Search, Waypoints } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getJobTrace, type JobTrace } from "../api/analytics-api";

const jobLabels: Record<JobTrace["events"][number]["job_kind"], string> = {
  ai_execution: "AI execution",
  automation_execution: "Automation",
  commerce_action: "Commerce approval/execution",
  document_ingestion: "Document ingestion",
  catalog_sync: "Catalog sync",
  catalog_webhook: "Catalog webhook",
  outbound_delivery: "Outbound delivery",
};

const correlationIdPattern = /^[A-Za-z0-9._:-]{8,64}$/;

export function JobTraceLookup({ request }: { request?: { correlationId: string } | null }) {
  const linkedCorrelationId = useSearchParams().get("trace");
  const [draft, setDraft] = useState<{ lookupId?: string; text: string }>();
  const trace = useMutation({ mutationFn: getJobTrace });
  const { mutate } = trace;
  const correlationId = draft && draft.lookupId === trace.variables ? draft.text : trace.variables ?? "";
  const headingRef = useRef<HTMLHeadingElement>(null);

  const openTrace = useCallback((id?: string | null) => {
    if (!id || !correlationIdPattern.test(id)) return;
    mutate(id);
    headingRef.current?.focus();
  }, [mutate]);

  useEffect(() => {
    openTrace(linkedCorrelationId);
  }, [linkedCorrelationId, openTrace]);

  useEffect(() => {
    openTrace(request?.correlationId);
  }, [request, openTrace]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = correlationId.trim();
    if (correlationIdPattern.test(id)) mutate(id);
  }

  return (
    <section aria-labelledby="job-trace-title" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-700"><Waypoints size={19} aria-hidden="true" /></span>
        <div className="min-w-0 flex-1">
          <h2 id="job-trace-title" ref={headingRef} tabIndex={-1} className="font-semibold text-slate-950">Request trace</h2>
          <p className="mt-1 text-sm text-slate-500">Follow a request across AI, automation, catalog, and message-delivery jobs using its support reference.</p>
          <form className="mt-4 flex flex-col gap-2 sm:flex-row" onSubmit={submit}>
            <label className="sr-only" htmlFor="trace-correlation-id">Correlation ID</label>
            <Input
              id="trace-correlation-id"
              autoComplete="off"
              minLength={8}
              maxLength={64}
              value={correlationId}
              onChange={(event) => setDraft({ lookupId: trace.variables, text: event.target.value })}
              placeholder="Paste correlation ID"
              className="min-w-0 flex-1 font-mono text-sm"
            />
            <Button type="submit" disabled={!correlationIdPattern.test(correlationId.trim()) || trace.isPending}>
              <Search size={15} aria-hidden="true" />{trace.isPending ? "Looking up…" : "Find trace"}
            </Button>
          </form>
          <p className="mt-2 text-xs text-slate-500">Results are limited to this workspace and include operational metadata only.</p>
          {trace.isPending && <p role="status" className="mt-3 text-sm text-slate-500">Loading request trace…</p>}
          {trace.isError && <p role="alert" className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">Could not load this request trace. Check the reference and try again.</p>}
          {trace.variables && (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="mt-3"
              disabled={trace.isPending}
              onClick={() => {
                if (trace.variables) mutate(trace.variables);
              }}
            >
              <RefreshCw size={14} aria-hidden="true" />
              {trace.isError ? "Retry last lookup" : "Refresh trace"}
            </Button>
          )}
          {trace.data && <TraceResult result={trace.data} />}
        </div>
      </div>
    </section>
  );
}

function traceStatus(event: JobTrace["events"][number]) {
  const [approval, execution] = event.status.split("/");
  const isCommerce = event.job_kind === "commerce_action" && Boolean(execution);
  const status = isCommerce && approval === "approved" ? execution : approval;

  const labels: Record<string, string> = {
    pending: "Awaiting approval",
    queued: "Approved · execution queued",
    running: "Approved · executing",
    succeeded: "Approved · execution succeeded",
    failed: "Approved · execution failed",
  };
  const label = isCommerce
    ? labels[status] ?? status.replaceAll("_", " ")
    : status.replaceAll("_", " ");
  if (status === "succeeded") return { label, tone: "bg-emerald-50 text-emerald-800" };
  if (["failed", "rejected", "expired"].includes(status)) {
    return { label, tone: "bg-rose-50 text-rose-800" };
  }
  if (status === "cancelled") return { label, tone: "bg-slate-100 text-slate-700" };
  return { label, tone: "bg-amber-50 text-amber-900" };
}

function formatTraceInterval(from: string, to: string): string | null {
  const seconds = Math.round((Date.parse(to) - Date.parse(from)) / 1000);
  if (!Number.isFinite(seconds) || seconds < 0) return null;
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60
    ? `${minutes}m ${seconds % 60}s`
    : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function TraceResult({ result }: { result: JobTrace }) {
  if (!result.events.length) {
    return <p role="status" className="mt-4 rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-600">No job records were found for this reference in the current workspace.</p>;
  }

  return (
    <div className="mt-4">
      <p className="mb-2 text-xs text-slate-500">{result.events.length} linked job{result.events.length === 1 ? "" : "s"} · checked {new Date(result.generated_at).toLocaleTimeString()}</p>
      {result.truncated && (
        <p role="status" className="mb-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-900">
          Showing the first {result.events.length} jobs. This request has more linked jobs.
        </p>
      )}
      <ol className="space-y-2" aria-label="Request job timeline">
        {result.events.map((event) => {
          const { label, tone } = traceStatus(event);
          const timeToStart = event.started_at && formatTraceInterval(event.created_at, event.started_at);
          const timeSinceStart = event.started_at && event.completed_at
            && formatTraceInterval(event.started_at, event.completed_at);
          return (
            <li key={`${event.job_kind}:${event.job_id}`} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-slate-200 p-3">
              <div className="min-w-0">
                <p className="font-medium text-slate-900">{jobLabels[event.job_kind]}</p>
                <p className="mt-1 break-all font-mono text-xs text-slate-500">{event.job_id}</p>
                <p className="mt-1 text-xs text-slate-500">Created {new Date(event.created_at).toLocaleString()}{event.completed_at ? ` · completed ${new Date(event.completed_at).toLocaleString()}` : ""}</p>
                {event.started_at && (
                  <p className="mt-1 text-xs text-slate-500">
                    Started {new Date(event.started_at).toLocaleString()}
                    {timeToStart && ` · ${timeToStart} from creation to start`}
                    {timeSinceStart && ` · ${timeSinceStart} from start to completion`}
                  </p>
                )}
                <p className="mt-1 text-xs text-slate-500">{event.max_attempts === null ? `${event.attempts} execution attempt${event.attempts === 1 ? "" : "s"}` : `${event.attempts}/${event.max_attempts} attempts`}{event.error_code ? ` · ${event.error_code}` : ""}</p>
              </div>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${tone}`}>{label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
