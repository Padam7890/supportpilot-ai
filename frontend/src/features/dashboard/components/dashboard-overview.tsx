"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, ArrowUpRight, CircleAlert, Clock3, Inbox, Plus, Users } from "lucide-react";
import { getDashboardStats, dashboardQueryKeys } from "../api/dashboard-api";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { StatusAlert } from "@/components/ui/status-alert";

export default function DashboardPage() {
  const stats = useQuery({ queryKey: dashboardQueryKeys.stats, queryFn: getDashboardStats });
  const data = stats.data;
  const maxVolume = Math.max(1, ...(data?.volume.map((day) => day.count) ?? []));

  return (
    <div className="space-y-7">
      <PageHeader eyebrow="Workspace overview" title="Good work starts here." description="A live view of your customer support operation." actions={<><Link href="/dashboard/customers"><Button variant="secondary"><Users size={16}/> Add customer</Button></Link><Link href="/dashboard/tickets"><Button><Plus size={17}/> New ticket</Button></Link></>} />
      {stats.isError && (
        <StatusAlert tone="error" title="Could not load workspace statistics">
          Try refreshing the page.
        </StatusAlert>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard title="All tickets" value={data?.total_tickets} icon={<Inbox size={18}/>} subtitle="Across your workspace" tone="blue" loading={stats.isPending}/>
        <StatCard title="Open" value={data?.open_tickets} icon={<CircleAlert size={18}/>} subtitle="Need a first response" tone="orange" loading={stats.isPending}/>
        <StatCard title="Pending" value={data?.pending_tickets} icon={<Clock3 size={18}/>} subtitle="Waiting on follow-up" tone="purple" loading={stats.isPending}/>
        <StatCard title="Resolved" value={data?.resolved_tickets} icon={<ArrowUpRight size={18}/>} subtitle="Successfully closed out" tone="green" loading={stats.isPending}/>
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.7fr)_minmax(290px,0.8fr)]">
        <Panel>
          <PanelHeader title="Ticket volume" description="New tickets over the last 30 days" action={<span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">Last 30 days</span>}/>
          <PanelBody>
            {stats.isPending ? <div className="h-64 animate-pulse rounded-xl bg-slate-100"/> : (
              <div className="flex h-64 items-end gap-1.5 border-b border-l border-slate-200 px-2 pb-1 pt-5 sm:gap-2">
                {(data?.volume ?? []).map((day, index) => {
                  const height = Math.max(2, (day.count / maxVolume) * 100);
                  return <div key={day.date} className="group relative flex h-full min-w-0 flex-1 items-end" title={`${day.date}: ${day.count} tickets`}><div className={`w-full rounded-t-md transition-colors group-hover:bg-blue-700 ${index === (data?.volume.length ?? 0) - 1 ? "bg-blue-600" : "bg-blue-200"}`} style={{ height: `${height}%` }}/></div>;
                })}
              </div>
            )}
            <div className="mt-3 flex justify-between text-[11px] text-slate-400"><span>30 days ago</span><span>New tickets per day</span><span>Today</span></div>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="By status" description="Current ticket distribution"/>
          <PanelBody className="space-y-5">
            {stats.isPending ? <div className="space-y-4">{[1, 2, 3, 4].map((item) => <div key={item} className="h-8 animate-pulse rounded bg-slate-100"/>)}</div> : Object.entries(data?.by_status ?? {}).length === 0 ? <EmptyState/> : Object.entries(data?.by_status ?? {}).map(([label, count]) => {
              const total = data?.total_tickets || 1;
              const width = `${Math.max(4, (count / total) * 100)}%`;
              return <div key={label}><div className="mb-2 flex justify-between text-sm"><span className="capitalize text-slate-600">{label}</span><span className="font-semibold text-slate-900">{count}</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-blue-600" style={{ width }}/></div></div>;
            })}
            <Link href="/dashboard/tickets" className="flex items-center gap-1 pt-1 text-sm font-semibold text-blue-700 hover:text-blue-900">View ticket queue <ArrowRight size={16}/></Link>
          </PanelBody>
        </Panel>
      </div>
      <Panel>
        <PanelHeader title="Priority overview" description="Tickets by urgency"/>
        <PanelBody className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(["urgent", "high", "normal", "low"] as const).map((priority) => <div key={priority} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/70 p-4"><div className="flex items-center gap-3"><span className={`size-2.5 rounded-full ${priority === "urgent" ? "bg-red-500" : priority === "high" ? "bg-orange-500" : priority === "normal" ? "bg-blue-500" : "bg-slate-400"}`}/><span className="text-sm font-medium capitalize text-slate-700">{priority}</span></div><span className="text-xl font-bold text-slate-900">{stats.isPending ? "—" : data?.by_priority[priority] ?? 0}</span></div>)}
        </PanelBody>
      </Panel>
    </div>
  );
}

function StatCard({ title, value, icon, subtitle, tone, loading }: { title: string; value?: number; icon: React.ReactNode; subtitle: string; tone: string; loading: boolean }) {
  const tones: Record<string, string> = { blue: "bg-blue-50 text-blue-700", orange: "bg-orange-50 text-orange-700", purple: "bg-violet-50 text-violet-700", green: "bg-emerald-50 text-emerald-700" };
  return <Panel className="p-5"><div className="flex items-start justify-between"><div><p className="helper-text font-medium">{title}</p>{loading ? <div className="mt-3 h-8 w-16 animate-pulse rounded bg-slate-100"/> : <p className="kpi-value mt-2">{value ?? 0}</p>}</div><span className={`grid size-10 place-items-center rounded-xl ${tones[tone]}`}>{icon}</span></div><p className="mt-4 flex items-center gap-1 text-xs text-slate-500">{tone === "green" ? <ArrowUpRight size={14} className="text-emerald-600"/> : <ArrowDownRight size={14} className="text-slate-400"/>}{subtitle}</p></Panel>;
}

function EmptyState() {
  return <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center"><p className="text-sm font-medium text-slate-700">No tickets yet</p><p className="mt-1 text-xs text-slate-500">Create a ticket to see your support activity here.</p></div>;
}
