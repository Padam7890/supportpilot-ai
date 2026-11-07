"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, CircleAlert, ClipboardCheck, LoaderCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getOperationalAlerts, analyticsQueryKeys } from "@/features/analytics/api/analytics-api";

export function OperationalAlerts() {
  const alerts = useQuery({
    queryKey: analyticsQueryKeys.operationalAlerts(),
    queryFn: getOperationalAlerts,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 60_000 : false,
    refetchIntervalInBackground: false,
  });

  return <section aria-labelledby="operational-alerts-title" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="text-xs font-bold uppercase tracking-[.14em] text-blue-700">Workspace activity</p>
        <h2 id="operational-alerts-title" className="mt-1 text-lg font-semibold text-slate-950">Operational activity</h2>
        <p className="mt-1 text-sm text-slate-500">Recent terminal failures, overdue background work, and requests awaiting review.</p>
      </div>
      <Button variant="secondary" size="sm" onClick={() => alerts.refetch()} disabled={alerts.isFetching} aria-label="Refresh operational alerts">
        <RefreshCw size={14} className={alerts.isFetching ? "animate-spin" : ""}/><span className="hidden sm:inline">Refresh</span>
      </Button>
    </header>

    {alerts.isPending ? <div role="status" className="mt-5 flex items-center gap-2 rounded-xl bg-slate-50 p-5 text-sm text-slate-500"><LoaderCircle size={16} className="animate-spin"/>Loading workspace activity…</div>
      : alerts.isError ? <div role="alert" className="mt-5 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><CircleAlert size={17} className="mt-0.5 shrink-0"/><span>Workspace activity could not be loaded. Refresh to try again.</span></div>
      : alerts.data.alerts.length === 0 ? <div className="mt-5 flex items-start gap-3 rounded-xl border border-emerald-100 bg-emerald-50/60 p-4"><ClipboardCheck size={18} className="mt-0.5 shrink-0 text-emerald-700"/><div><p className="text-sm font-semibold text-emerald-950">No recent issues</p><p className="mt-1 text-xs text-emerald-800">No recent terminal failures, overdue jobs in the monitored queues, or commerce requests awaiting review.</p></div></div>
      : <ul className="mt-5 grid gap-3 sm:grid-cols-2">
        {alerts.data.alerts.map((alert) => <li key={alert.code} className={`rounded-xl border p-4 ${alert.severity === "review" ? "border-amber-200 bg-amber-50/70" : "border-rose-100 bg-rose-50/50"}`}>
          <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className={`text-sm font-semibold ${alert.severity === "review" ? "text-amber-950" : "text-rose-950"}`}>{alert.title}</p><p className="mt-1 text-xs leading-5 text-slate-600">{alert.description}</p></div><span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold tabular-nums ${alert.severity === "review" ? "bg-amber-100 text-amber-900" : "bg-rose-100 text-rose-900"}`}>{alert.count}</span></div>
          <Link href={alert.href} className="mt-3 inline-flex min-h-8 items-center gap-1 text-xs font-semibold text-blue-800 underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700">{alert.action_label}<ArrowUpRight size={13}/></Link>
        </li>)}
      </ul>}
    {alerts.data && <p className="mt-4 text-[11px] text-slate-500">Updated {new Date(alerts.data.generated_at).toLocaleTimeString()}</p>}
  </section>;
}
