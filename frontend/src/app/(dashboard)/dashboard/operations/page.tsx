"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, CheckCircle2, CircleAlert, Database, RefreshCw, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getSystemReadiness } from "@/features/dashboard/api/system-status-api";
import { CommerceActionsWorkspace } from "@/features/commerce-actions/components/commerce-actions-workspace";
import { ApiError } from "@/lib/api/errors";

export default function OperationsPage() {
  const readiness = useQuery({
    queryKey: ["system-readiness"],
    queryFn: getSystemReadiness,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
  const checkedAt = readiness.dataUpdatedAt ? new Date(readiness.dataUpdatedAt).toLocaleTimeString() : null;

  return <div className="mx-auto max-w-5xl space-y-7">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-[.16em] text-blue-700">Workspace administration</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Operations</h1><p className="mt-2 text-sm text-slate-500">Live readiness checks for the services that support your workspace.</p></div><Button variant="secondary" onClick={() => readiness.refetch()} disabled={readiness.isFetching}><RefreshCw size={15} className={readiness.isFetching ? "animate-spin" : ""}/>Refresh status</Button></header>
    {readiness.isPending && <div role="status" className="h-36 animate-pulse rounded-2xl bg-slate-100"/>}
    {readiness.isError && <div role="alert" className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-amber-950"><CircleAlert size={20} className="mt-0.5 shrink-0"/><div><p className="font-semibold">Readiness could not be confirmed</p><p className="mt-1 text-sm">{readiness.error instanceof ApiError ? readiness.error.message : "The API could not confirm that required services are available. Try refreshing in a moment."}</p></div></div>}
    {readiness.data && <>
      <section aria-label="Overall readiness" className="flex items-start gap-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-5"><span className="grid size-11 shrink-0 place-items-center rounded-xl bg-white text-emerald-700"><CheckCircle2 size={22}/></span><div><p className="font-semibold text-emerald-950">Core services ready</p><p className="mt-1 text-sm text-emerald-800">Database and Redis checks passed.</p>{checkedAt && <p className="mt-2 text-xs text-emerald-700">Last checked at {checkedAt}</p>}</div></section>
      <section aria-label="Service checks" className="grid gap-4 sm:grid-cols-2"><ServiceCard title="PostgreSQL database" description="Workspace records and durable background jobs" icon={<Database size={18}/>} state={readiness.data.checks.database}/><ServiceCard title="Redis" description="Authentication limits and application coordination" icon={<Server size={18}/>} state={readiness.data.checks.redis}/></section>
    </>}
    <CommerceActionsWorkspace />
    <p className="flex items-start gap-2 rounded-xl bg-slate-50 p-4 text-xs leading-5 text-slate-500"><Activity size={15} className="mt-0.5 shrink-0"/>The readiness panel reports only checks returned by the readiness API. It does not display worker throughput or provider health that the system does not currently measure.</p>
  </div>;
}

function ServiceCard({ title, description, icon, state }: { title: string; description: string; icon: React.ReactNode; state: "connected" }) {
  return <article className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between"><span className="grid size-10 place-items-center rounded-xl bg-blue-50 text-blue-700">{icon}</span><span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold capitalize text-emerald-700"><span className="size-1.5 rounded-full bg-emerald-500"/>{state}</span></div><h2 className="mt-4 font-semibold">{title}</h2><p className="mt-1 text-sm text-slate-500">{description}</p></article>;
}
