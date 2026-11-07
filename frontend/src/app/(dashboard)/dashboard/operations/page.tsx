"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { Activity, CheckCircle2, CircleAlert, Database, RefreshCw, Server, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getSystemReadiness, getWorkerHealth, type WorkerHealth } from "@/features/dashboard/api/system-status-api";
import { CommerceActionsWorkspace } from "@/features/commerce-actions/components/commerce-actions-workspace";
import { OperationalAlerts } from "@/features/analytics/components/operational-alerts";
import { FailedBackgroundJobs } from "@/features/analytics/components/failed-background-jobs";
import { ApiError } from "@/lib/api/errors";

export default function OperationsPage() {
  const readiness = useQuery({
    queryKey: ["system-readiness"],
    queryFn: getSystemReadiness,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
  const worker = useQuery({
    queryKey: ["worker-health"],
    queryFn: getWorkerHealth,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
  const checkedAt = readiness.dataUpdatedAt ? new Date(readiness.dataUpdatedAt).toLocaleTimeString() : null;

  return <div className="mx-auto max-w-5xl space-y-7">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-[.16em] text-blue-700">Workspace administration</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Operations</h1><p className="mt-2 text-sm text-slate-500">Live readiness checks for the services that support your workspace.</p></div><Button variant="secondary" onClick={() => { void readiness.refetch(); void worker.refetch(); }} disabled={readiness.isFetching || worker.isFetching}><RefreshCw size={15} className={readiness.isFetching || worker.isFetching ? "animate-spin" : ""}/>Refresh status</Button></header>
    {readiness.isPending && <div role="status" className="h-36 animate-pulse rounded-2xl bg-slate-100"/>}
    {readiness.isError && <div role="alert" className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-amber-950"><CircleAlert size={20} className="mt-0.5 shrink-0"/><div><p className="font-semibold">Readiness could not be confirmed</p><p className="mt-1 text-sm">{readiness.error instanceof ApiError ? readiness.error.message : "The API could not confirm that required services are available. Try refreshing in a moment."}</p></div></div>}
    {readiness.data && <>
      <section aria-label="Overall readiness" className="flex items-start gap-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-5"><span className="grid size-11 shrink-0 place-items-center rounded-xl bg-white text-emerald-700"><CheckCircle2 size={22}/></span><div><p className="font-semibold text-emerald-950">Core services ready</p><p className="mt-1 text-sm text-emerald-800">Database and Redis checks passed.</p>{checkedAt && <p className="mt-2 text-xs text-emerald-700">Last checked at {checkedAt}</p>}</div></section>
      <section aria-label="Service checks" className="grid gap-4 sm:grid-cols-2"><ServiceCard title="PostgreSQL database" description="Workspace records and durable background jobs" icon={<Database size={18}/>} state={readiness.data.checks.database}/><ServiceCard title="Redis" description="Authentication limits and application coordination" icon={<Server size={18}/>} state={readiness.data.checks.redis}/></section>
    </>}
    <WorkerCard worker={worker}/>
    <OperationalAlerts />
    <FailedBackgroundJobs />
    <div id="commerce-actions"><CommerceActionsWorkspace /></div>
    <p className="flex items-start gap-2 rounded-xl bg-slate-50 p-4 text-xs leading-5 text-slate-500"><Activity size={15} className="mt-0.5 shrink-0"/>The readiness panel reports only checks returned by the readiness API. It does not display worker throughput or provider health that the system does not currently measure.</p>
  </div>;
}

function WorkerCard({ worker }: { worker: UseQueryResult<WorkerHealth> }) {
  const active = !worker.isError && worker.data?.status === "active";
  const tone = active ? "border-emerald-200 bg-emerald-50 text-emerald-950" : "border-amber-200 bg-amber-50 text-amber-950";
  return <section aria-label="Background worker status" className={`rounded-2xl border p-5 ${tone}`}>
    <div className="flex items-start gap-4">
      <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-white/80 text-current"><Workflow size={21}/></span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1"><h2 className="font-semibold text-current">Background worker</h2>
          {worker.data && !worker.isError && <span className="inline-flex items-center gap-1.5 rounded-full bg-white/80 px-2.5 py-1 text-xs font-semibold"><span className={`size-1.5 rounded-full ${active ? "bg-emerald-500" : "bg-amber-500"}`}/>{active ? "Active" : "Inactive"}</span>}
          {worker.isPending && <span className="text-xs font-medium">Checking…</span>}
          {worker.isError && <span className="text-xs font-semibold">Status unavailable</span>}
        </div>
        <p className="mt-1 text-sm">{worker.isError
          ? "Worker status could not be checked. Redis may be unavailable; refresh to retry."
          : worker.data?.status === "active"
            ? `${worker.data.active_workers} worker process${worker.data.active_workers === 1 ? "" : "es"} reported a recent heartbeat. Durable AI, catalog, and delivery jobs can be processed.`
            : worker.data?.status === "inactive"
              ? "No worker heartbeat was received recently. Queued AI, catalog, and outbound delivery jobs may wait until a worker is running."
              : "Checking whether a background worker is reporting in."}</p>
        {worker.data && !worker.isError && <p className="mt-2 text-xs opacity-80">Checked {new Date(worker.data.checked_at).toLocaleTimeString()}</p>}
      </div>
      {(worker.isError || worker.data?.status === "inactive") && <CircleAlert size={19} className="mt-1 shrink-0" aria-hidden="true"/>}
    </div>
  </section>;
}

function ServiceCard({ title, description, icon, state }: { title: string; description: string; icon: React.ReactNode; state: "connected" }) {
  return <article className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between"><span className="grid size-10 place-items-center rounded-xl bg-blue-50 text-blue-700">{icon}</span><span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold capitalize text-emerald-700"><span className="size-1.5 rounded-full bg-emerald-500"/>{state}</span></div><h2 className="mt-4 font-semibold">{title}</h2><p className="mt-1 text-sm text-slate-500">{description}</p></article>;
}
