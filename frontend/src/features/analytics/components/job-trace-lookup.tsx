"use client";

import { useMutation } from "@tanstack/react-query";
import { Search, Waypoints } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
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

export function JobTraceLookup({ request }: { request?: { correlationId: string } | null }) {
  const [correlationId, setCorrelationId] = useState("");
  const trace = useMutation({ mutationFn: getJobTrace });
  const { mutate } = trace;
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (!request) return;
    setCorrelationId(request.correlationId);
    mutate(request.correlationId);
    headingRef.current?.focus();
  }, [request, mutate]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = correlationId.trim();
    if (id.length >= 8 && id.length <= 64) trace.mutate(id);
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
              onChange={(event) => setCorrelationId(event.target.value)}
              placeholder="Paste correlation ID"
              className="min-w-0 flex-1 font-mono text-sm"
            />
            <Button type="submit" disabled={correlationId.trim().length < 8 || trace.isPending}>
              <Search size={15} aria-hidden="true" />{trace.isPending ? "Looking up…" : "Find trace"}
            </Button>
          </form>
          <p className="mt-2 text-xs text-slate-500">Results are limited to this workspace and include operational metadata only.</p>
          {trace.isPending && <p role="status" className="mt-3 text-sm text-slate-500">Loading request trace…</p>}
          {trace.isError && <p role="alert" className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">Could not load this request trace. Check the reference and try again.</p>}
          {trace.data && <TraceResult result={trace.data} />}
        </div>
      </div>
    </section>
  );
}

function TraceResult({ result }: { result: JobTrace }) {
  if (!result.events.length) {
    return <p role="status" className="mt-4 rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-600">No job records were found for this reference in the current workspace.</p>;
  }

  return (
    <div className="mt-4">
      <p className="mb-2 text-xs text-slate-500">{result.events.length} linked job{result.events.length === 1 ? "" : "s"} · checked {new Date(result.generated_at).toLocaleTimeString()}</p>
      <ol className="space-y-2" aria-label="Request job timeline">
        {result.events.map((event) => {
          const completed = event.status === "succeeded";
          const failed = ["failed", "rejected", "expired"].includes(event.status);
          const tone = completed ? "bg-emerald-50 text-emerald-800" : failed ? "bg-rose-50 text-rose-800" : "bg-amber-50 text-amber-900";
          return (
            <li key={`${event.job_kind}:${event.job_id}`} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-slate-200 p-3">
              <div className="min-w-0">
                <p className="font-medium text-slate-900">{jobLabels[event.job_kind]}</p>
                <p className="mt-1 break-all font-mono text-xs text-slate-500">{event.job_id}</p>
                <p className="mt-1 text-xs text-slate-500">Created {new Date(event.created_at).toLocaleString()}{event.completed_at ? ` · completed ${new Date(event.completed_at).toLocaleString()}` : ""}</p>
                <p className="mt-1 text-xs text-slate-500">{event.max_attempts === null ? `${event.attempts} execution attempt${event.attempts === 1 ? "" : "s"}` : `${event.attempts}/${event.max_attempts} attempts`}{event.error_code ? ` · ${event.error_code}` : ""}</p>
              </div>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${tone}`}>{event.status.replaceAll("_", " ")}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
