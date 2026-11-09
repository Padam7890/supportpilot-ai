"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, CircleDollarSign, Clock3, Sparkles } from "lucide-react";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { analyticsQueryKeys, getAIUsage } from "@/features/analytics/api/analytics-api";
import { aiAgentAuditKey, aiAgentsKey, getAIAgentAudit, listAIAgents } from "../api/ai-agent-api";
import { formatDateTime } from "@/lib/utils";

function dateValue(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

export function AIAgentPerformancePage({ agentId }: { agentId: string }) {
  const user = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const canView = ["owner", "admin"].includes(user.data?.role ?? "");
  const agents = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents });
  const audit = useQuery({ queryKey: aiAgentAuditKey(agentId), queryFn: () => getAIAgentAudit(agentId), enabled: canView });
  const range = useQuery({
    queryKey: ["ai-agent-performance-range", agentId],
    queryFn: () => {
      const end = new Date();
      const start = new Date(end);
      start.setDate(start.getDate() - 29);
      return { start: dateValue(start), end: dateValue(end) };
    },
    staleTime: Number.POSITIVE_INFINITY,
  });
  const usage = useQuery({
    queryKey: range.data ? analyticsQueryKeys.usage(range.data.start, range.data.end) : ["analytics", "ai-usage", "pending"],
    queryFn: () => {
      if (!range.data) throw new Error("Performance date range is unavailable");
      return getAIUsage(range.data.start, range.data.end);
    },
    enabled: Boolean(range.data && canView),
  });
  const agent = agents.data?.items.find((item) => item.id === agentId);
  const botUsage = usage.data?.bots?.find((item) => item.bot_id === agentId);

  return <div className="space-y-5">
    <Link href="/dashboard/ai/agents" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft size={16}/>Back to AI bots</Link>
    <header><p className="flex items-center gap-2 text-sm font-medium text-primary"><Bot size={16}/> Bot insights</p><h1 className="mt-1 text-2xl font-semibold tracking-tight">{agent?.name ?? "AI bot"}</h1><p className="mt-1 text-sm text-muted-foreground">Performance and configuration history in one place.</p></header>
    {!canView && user.data && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">You do not have permission to view bot performance.</p>}
    {agents.isError && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">Bot details could not be loaded.</p>}
    {usage.isPending && <p role="status" className="text-sm text-muted-foreground">Loading performance…</p>}
    {usage.isError && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">Bot performance could not be loaded. Refresh to try again.</p>}
    {usage.isSuccess && !botUsage && <div className="rounded-xl border border-dashed p-8 text-center"><Sparkles className="mx-auto size-8 text-muted-foreground"/><h2 className="mt-3 font-semibold">No activity yet</h2><p className="mt-1 text-sm text-muted-foreground">This bot has no recorded AI executions in the last 30 days.</p></div>}
    {botUsage && <>
      <section aria-label="Bot performance metrics" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric title="Executions" value={botUsage.executions.toLocaleString()} detail={`${botUsage.succeeded} succeeded · ${botUsage.failed} failed`} icon={<Sparkles/>}/>
        <Metric title="Tokens used" value={(botUsage.prompt_tokens + botUsage.completion_tokens).toLocaleString()} detail={`${botUsage.prompt_tokens.toLocaleString()} input · ${botUsage.completion_tokens.toLocaleString()} output`} icon={<Bot/>}/>
        <Metric title="Average latency" value={botUsage.average_latency_ms == null ? "—" : `${botUsage.average_latency_ms.toLocaleString()} ms`} detail={botUsage.p95_latency_ms == null ? "No percentile data" : `P95 · ${botUsage.p95_latency_ms.toLocaleString()} ms`} icon={<Clock3/>}/>
        <Metric title="Estimated cost" value={botUsage.estimated_cost_usd == null ? "Not configured" : `$${botUsage.estimated_cost_usd.toFixed(4)}`} detail="Based on configured provider rates" icon={<CircleDollarSign/>}/>
      </section>
      <Panel><PanelHeader title="Execution health" description="Summary of persisted AI executions attributed to this bot."/><PanelBody className="grid gap-5 sm:grid-cols-3"><div><p className="text-xs text-muted-foreground">Success rate</p><p className="mt-1 text-xl font-semibold">{botUsage.executions ? `${Math.round((botUsage.succeeded / botUsage.executions) * 100)}%` : "—"}</p></div><div><p className="text-xs text-muted-foreground">Completed successfully</p><p className="mt-1 text-xl font-semibold">{botUsage.succeeded.toLocaleString()}</p></div><div><p className="text-xs text-muted-foreground">Failed executions</p><p className="mt-1 text-xl font-semibold">{botUsage.failed.toLocaleString()}</p></div></PanelBody></Panel>
    </>}
    <Panel><PanelHeader title="Configuration history" description="Recent changes to this bot. Instruction text is never included in the audit history."/><PanelBody>
      {audit.isPending && <p role="status" className="text-sm text-muted-foreground">Loading history…</p>}
      {audit.isError && <p role="alert" className="rounded-lg bg-destructive/5 p-3 text-sm text-destructive">Configuration history could not be loaded.</p>}
      {audit.data?.items.length === 0 && <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">No configuration changes recorded yet.</p>}
      {audit.data?.items && audit.data.items.length > 0 && <ol className="divide-y rounded-lg border">{audit.data.items.map((entry) => <li key={entry.id} className="flex flex-wrap items-start justify-between gap-3 p-4"><div><p className="text-sm font-medium">{eventLabel(entry.event_type)}</p><p className="mt-1 text-xs text-muted-foreground">{entry.actor_name} · version {entry.config_version}{changedFields(entry.details).length ? ` · ${changedFields(entry.details).join(", ")}` : ""}</p></div><time className="shrink-0 text-xs text-muted-foreground" dateTime={entry.created_at}>{formatDateTime(entry.created_at)}</time></li>)}</ol>}
    </PanelBody></Panel>
    <div><Link className="inline-flex h-9 items-center gap-2 rounded-md border px-3.5 text-sm font-medium hover:bg-muted" href={`/dashboard/ai?ai_agent_id=${encodeURIComponent(agentId)}`}><Sparkles size={16}/>Test bot</Link></div>
  </div>;
}

function eventLabel(eventType: string) {
  const labels: Record<string, string> = { created: "Bot created", updated: "Bot settings updated", knowledge_bases_changed: "Knowledge base assignments changed", activated: "Bot activated", deactivated: "Bot deactivated" };
  return labels[eventType] ?? "Bot configuration changed";
}

function changedFields(details: Record<string, unknown>) {
  const fields = details.changed_fields;
  return Array.isArray(fields) ? fields.filter((field): field is string => typeof field === "string").map((field) => field === "is_default" ? "workspace default" : field.replaceAll("_", " ")) : [];
}

function Metric({ title, value, detail, icon }: { title: string; value: string; detail: string; icon: ReactNode }) {
  return <Panel><PanelBody className="p-4"><div className="flex items-center justify-between text-muted-foreground"><p className="text-sm">{title}</p><span className="[&_svg]:size-4">{icon}</span></div><p className="mt-3 truncate text-2xl font-semibold tracking-tight">{value}</p><p className="mt-1 text-xs text-muted-foreground">{detail}</p></PanelBody></Panel>;
}
