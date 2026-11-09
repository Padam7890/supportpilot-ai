"use client";

import { Input } from "@/components/ui";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, BarChart3, CircleDollarSign, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { listAIExecutions } from "@/features/ai/api/ai-api";
import {
  analyticsQueryKeys,
  getIntegrationDeliveryAnalytics,
  getAIUsage,
  getCommerceApprovalAnalytics,
  getSupportResponseAnalytics,
  getEvaluationSummary,
  submitEvaluation,
  type AIEvaluationCreate,
  type CommerceApprovalAnalytics,
} from "../api/analytics-api";
import { getRecommendationAnalytics, recommendationQueryKeys } from "@/features/recommendations/api/recommendation-api";
import { automationKey, getAutomationMetrics, type AutomationMetrics } from "@/features/automations/api/automation-api";

function dateValue(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function dateRangeError(start: string, end: string): string | null {
  if (!start || !end) return "Choose both a start date and an end date.";
  const startTime = Date.parse(start);
  const endTime = Date.parse(end);
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) return "Choose valid dates.";
  if (startTime > endTime) return "The start date must be on or before the end date.";
  const millisecondsPerDay = 86_400_000;
  if ((endTime - startTime) / millisecondsPerDay > 365) return "Choose a range of 366 days or fewer.";
  return null;
}

export function AnalyticsDashboard() {
  const now = new Date();
  const [endDate, setEndDate] = useState(dateValue(now));
  const [startDate, setStartDate] = useState(() => {
    const start = new Date(now);
    start.setDate(start.getDate() - 29);
    return dateValue(start);
  });
  const [executionId, setExecutionId] = useState("");
  const [rating, setRating] = useState<AIEvaluationCreate["rating"]>("helpful");
  const [category, setCategory] = useState<AIEvaluationCreate["category"]>();
  const rangeError = dateRangeError(startDate, endDate);
  const queryClient = useQueryClient();
  const usage = useQuery({
    queryKey: analyticsQueryKeys.usage(startDate, endDate),
    queryFn: () => getAIUsage(startDate, endDate),
    enabled: rangeError === null,
  });
  const evaluations = useQuery({
    queryKey: analyticsQueryKeys.evaluations(startDate, endDate),
    queryFn: () => getEvaluationSummary(startDate, endDate),
    enabled: rangeError === null,
  });
  const deliveryAnalytics = useQuery({
    queryKey: analyticsQueryKeys.integrationDeliveries(startDate, endDate),
    queryFn: () => getIntegrationDeliveryAnalytics(startDate, endDate),
    enabled: rangeError === null,
  });
  const commerceApprovals = useQuery({
    queryKey: analyticsQueryKeys.commerceApprovals(startDate, endDate),
    queryFn: () => getCommerceApprovalAnalytics(startDate, endDate),
    enabled: rangeError === null,
  });
  const supportResponses = useQuery({
    queryKey: analyticsQueryKeys.supportResponses(startDate, endDate),
    queryFn: () => getSupportResponseAnalytics(startDate, endDate),
    enabled: rangeError === null,
  });
  const recommendations = useQuery({
    queryKey: recommendationQueryKeys.analytics(startDate, endDate),
    queryFn: () => getRecommendationAnalytics(startDate, endDate),
    enabled: rangeError === null,
  });
  const automationMetrics = useQuery({
    queryKey: [...automationKey, "metrics", startDate, endDate],
    queryFn: () => getAutomationMetrics(30, startDate, endDate),
    enabled: rangeError === null,
  });
  const executions = useQuery({ queryKey: ["ai-executions", "analytics"], queryFn: () => listAIExecutions(100, 0), enabled: rangeError === null });
  const eligible = useMemo(
    () => (executions.data?.items ?? []).filter((item) => item.kind === "reply_draft" && item.status === "succeeded"),
    [executions.data],
  );
  const evaluate = useMutation({
    mutationFn: () => submitEvaluation({ execution_id: executionId, rating, ...(category ? { category } : {}) }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["analytics", "evaluations"] });
    },
  });
  const maxDaily = Math.max(1, ...(usage.data?.daily.map((point) => point.prompt_tokens + point.completion_tokens) ?? []));

  return <div className="space-y-7">
    <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><p className="sidebar-group text-[var(--text-accent)]">Workspace insights</p><h1 className="page-title mt-1">Analytics</h1><p className="page-subtitle mt-2">AI usage, recommendation activity, workflow health, and teammate feedback.</p></div>
      <div className="flex flex-wrap items-end gap-3"><label className="text-xs font-semibold text-slate-600">From<Input aria-label="Analytics start date" type="date" value={startDate} max={endDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"/></label><label className="text-xs font-semibold text-slate-600">To<Input aria-label="Analytics end date" type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)} className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"/></label></div>
    </header>

    {rangeError ? (
      <p role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{rangeError}</p>
    ) : <>
    {(usage.isError || evaluations.isError) && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">Analytics could not be loaded. Refresh the page or adjust the selected date range.</div>}
      <section aria-label="AI usage summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Metric available={Boolean(usage.data)} loading={usage.isPending} title="AI requests" value={usage.data?.executions.toLocaleString() ?? "0"} detail={`${usage.data?.succeeded ?? 0} completed · ${usage.data?.failed ?? 0} failed`} icon={<Sparkles size={18}/>} />
        <Metric available={Boolean(usage.data)} loading={usage.isPending} title="Tokens used" value={usage.data?.total_tokens.toLocaleString() ?? "0"} detail={`${usage.data?.prompt_tokens.toLocaleString() ?? "0"} input · ${usage.data?.completion_tokens.toLocaleString() ?? "0"} output`} icon={<BarChart3 size={18}/>} />
        <Metric available={Boolean(usage.data)} loading={usage.isPending} title="Estimated AI cost" value={usage.data?.estimated_cost_usd == null ? "Not configured" : `$${usage.data.estimated_cost_usd.toFixed(4)}`} detail={usage.data?.estimated_cost_usd == null ? "Set provider token rates to estimate cost" : "Based on configured input and output rates"} icon={<CircleDollarSign size={18}/>} />
        <Metric available={Boolean(evaluations.data)} loading={evaluations.isPending} title="Helpful feedback" value={evaluations.data?.helpful_rate == null ? "No ratings" : `${Math.round(evaluations.data.helpful_rate * 100)}%`} detail={`${evaluations.data?.rated ?? 0} teammate ratings`} icon={<ThumbsUp size={18}/>} />
        <Metric available={Boolean(usage.data)} loading={usage.isPending} title="Document citation coverage" value={usage.data?.document_citation_rate == null ? "No model replies" : `${Math.round(usage.data.document_citation_rate * 100)}%`} detail={usage.data?.document_citation_rate == null ? "No eligible model-generated responses" : `${usage.data.responses_with_document_citations} cited of ${usage.data.model_backed_responses} model-generated responses`} icon={<ShieldCheck size={18}/>} />
      </section>

      <section aria-label="AI monitoring and cost coverage" className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-slate-900">AI cost monitoring</h2>
        <p className="mt-2 text-sm text-slate-600">
          Costs are estimates from configured model-specific rates and provider-reported tokens,
          not provider invoices. Unknown usage or unpriced models cause the total to show as
          unavailable rather than an incorrect zero. This view excludes untracked embeddings,
          routing calls, and retries unless those calls are recorded as executions.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Successful executions</p><p className="text-xl font-semibold">{usage.data?.succeeded.toLocaleString() ?? "—"}</p></div>
          <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Failed executions</p><p className="text-xl font-semibold">{usage.data?.failed.toLocaleString() ?? "—"}</p></div>
          <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Execution failure rate</p><p className="text-xl font-semibold">{usage.data?.executions ? `${((usage.data.failed / usage.data.executions) * 100).toFixed(1)}%` : "—"}</p></div>
        </div>
      </section>

      {usage.data?.input_cost_per_million_usd != null && usage.data.output_cost_per_million_usd != null && (
        <p className="text-xs text-slate-600">
          AI cost estimate uses recorded tokens at ${usage.data.input_cost_per_million_usd} USD per million input tokens
          and ${usage.data.output_cost_per_million_usd} USD per million output tokens.
        </p>
      )}

      <section aria-labelledby="ai-bot-usage-title" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 id="ai-bot-usage-title" className="font-semibold">AI bot activity</h2><p className="mt-1 text-xs text-slate-500">Execution, token, cost, and response-time totals by bot for the selected date range.</p></div>
          <span className="rounded-lg bg-violet-50 p-2 text-violet-700"><Sparkles size={18} aria-hidden="true"/></span>
        </div>
        {!usage.data ? <p className="mt-5 text-sm text-slate-500">{usage.isPending ? "Loading AI usage…" : "Bot activity unavailable."}</p> : !usage.data.bots.length ? <p className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No bot executions were recorded in this date range.</p> : <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead><tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500"><th scope="col" className="pb-3 pr-4">Bot</th><th scope="col" className="pb-3 px-3">Runs</th><th scope="col" className="pb-3 px-3">Completed</th><th scope="col" className="pb-3 px-3">Failed</th><th scope="col" className="pb-3 px-3">Tokens</th><th scope="col" className="pb-3 px-3">Est. cost</th><th scope="col" className="pb-3 px-3">Avg. latency</th><th scope="col" className="pb-3 pl-3">P95 latency</th></tr></thead>
            <tbody>{usage.data.bots.map((bot) => <tr key={bot.bot_id} className="border-b border-slate-100 last:border-0"><th scope="row" className="py-3 pr-4 font-semibold text-slate-900">{bot.bot_name}</th><td className="px-3 py-3 text-slate-700">{bot.executions.toLocaleString()}</td><td className="px-3 py-3 text-emerald-800">{bot.succeeded.toLocaleString()}</td><td className={`px-3 py-3 ${bot.failed ? "text-rose-700" : "text-slate-500"}`}>{bot.failed.toLocaleString()}</td><td className="px-3 py-3 text-slate-700">{(bot.prompt_tokens + bot.completion_tokens).toLocaleString()}</td><td className="px-3 py-3 text-slate-700">{bot.estimated_cost_usd == null ? "Not configured" : `$${bot.estimated_cost_usd.toFixed(4)}`}</td><td className="pl-3 py-3 text-slate-700">{bot.average_latency_ms == null ? "—" : `${bot.average_latency_ms.toLocaleString()} ms`}</td>
              <td className="pl-3 py-3 text-slate-700">
                {bot.p95_latency_ms == null ? "—" : `${bot.p95_latency_ms.toLocaleString()} ms`}
                {bot.timed_execution_count ? <span className="block text-xs text-slate-500">{bot.timed_execution_count.toLocaleString()} timed runs</span> : null}
              </td></tr>)}</tbody>
          </table>
        </div>}
      </section>

      <section id="ai-errors-title" aria-labelledby="ai-errors-heading" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 id="ai-errors-heading" className="font-semibold">AI execution failures</h2><p className="mt-1 text-xs text-slate-500">Stable error codes for executions that exhausted their retry policy in the selected date range.</p></div>
          <span className="rounded-lg bg-rose-50 p-2 text-rose-700"><Activity size={18} aria-hidden="true"/></span>
        </div>
        {!usage.data ? <p className="mt-5 text-sm text-slate-500">{usage.isPending ? "Loading AI usage…" : "Failure metrics unavailable."}</p> : !usage.data.top_errors.length ? <p className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No terminal AI execution failures were recorded in this date range.</p> : <ul className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {usage.data.top_errors.map((item) => <li key={item.code} className="flex items-center justify-between gap-3 rounded-xl border border-rose-100 bg-rose-50/50 px-3 py-2.5 text-sm"><code className="min-w-0 truncate text-rose-900">{item.code}</code><span className="shrink-0 rounded-full bg-white px-2 py-1 text-xs font-semibold text-rose-900">{item.count}</span></li>)}
        </ul>}
        {usage.data?.daily.some((day) => day.failed > 0) && <p className="mt-3 text-xs text-slate-500">Daily totals include {usage.data.daily.reduce((sum, day) => sum + day.failed, 0).toLocaleString()} failed runs across the selected period.</p>}
      </section>

      <section aria-label="Automation run health" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 className="font-semibold">Automation run health</h2><p className="mt-1 text-xs text-slate-500">Tenant-scoped workflow executions for the selected date range.</p></div>
          <span className="rounded-lg bg-violet-50 p-2 text-violet-700"><BarChart3 size={18} aria-hidden="true"/></span>
        </div>
        {automationMetrics.isPending ? <p role="status" className="mt-5 text-sm text-slate-500">Loading automation metrics…</p>
          : automationMetrics.isError ? <p role="alert" className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-800">Automation metrics could not be loaded. Other analytics remain available.</p>
          : !automationMetrics.data || automationMetrics.data.total === 0 ? <p className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No workflow executions in this date range.</p>
              : <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-5">
                <AutomationMetric label="Total runs" value={automationMetrics.data?.total.toLocaleString() ?? "0"}/>
                <AutomationMetric label="Succeeded" value={automationMetrics.data?.succeeded.toLocaleString() ?? "0"} tone="green"/>
                <AutomationMetric label="In progress" value={((automationMetrics.data?.queued ?? 0) + (automationMetrics.data?.running ?? 0)).toLocaleString()} tone="blue"/>
                <AutomationMetric label="Failed" value={automationMetrics.data?.failed.toLocaleString() ?? "0"} tone={(automationMetrics.data?.failed ?? 0) > 0 ? "red" : "neutral"}/>
                <AutomationMetric label="Avg. duration" value={automationMetrics.data?.average_duration_ms == null ? "—" : `${automationMetrics.data.average_duration_ms.toLocaleString()} ms`}/>
              </div>}
        {!automationMetrics.isPending && !automationMetrics.isError && automationMetrics.data && automationMetrics.data.total > 0 && <AutomationTrend daily={automationMetrics.data.daily} topErrors={automationMetrics.data.top_errors}/>}
      </section>

      <section id="channel-delivery" aria-labelledby="delivery-health-title" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 id="delivery-health-title" className="font-semibold">Channel delivery health</h2><p className="mt-1 text-xs text-slate-500">Outbound integration deliveries recorded in this workspace during the selected date range.</p></div>
          <span className="rounded-lg bg-amber-50 p-2 text-amber-800"><BarChart3 size={18} aria-hidden="true"/></span>
        </div>
        {deliveryAnalytics.isPending ? <p role="status" className="mt-5 text-sm text-slate-500">Loading delivery metrics…</p>
          : deliveryAnalytics.isError ? <p role="alert" className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-800">Channel delivery metrics could not be loaded. Other analytics remain available.</p>
          : deliveryAnalytics.data?.total === 0 ? <p className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No outbound integration deliveries were recorded in this date range.</p>
          : <>
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
              <AutomationMetric label="Total deliveries" value={deliveryAnalytics.data?.total.toLocaleString() ?? "0"}/>
              <AutomationMetric label="Succeeded" value={deliveryAnalytics.data?.succeeded.toLocaleString() ?? "0"} tone="green"/>
              <AutomationMetric label="Failed" value={deliveryAnalytics.data?.failed.toLocaleString() ?? "0"} tone={(deliveryAnalytics.data?.failed ?? 0) > 0 ? "red" : "neutral"}/>
              <AutomationMetric label="Queued" value={deliveryAnalytics.data?.queued.toLocaleString() ?? "0"} tone="blue"/>
              <AutomationMetric label="Running" value={deliveryAnalytics.data?.running.toLocaleString() ?? "0"} tone="blue"/>
              <AutomationMetric label="Avg. attempts" value={deliveryAnalytics.data?.average_attempts?.toFixed(2) ?? "—"}/>
            </div>
            <div className="mt-5 flex flex-wrap gap-2" aria-label="Delivery counts by provider">
              {deliveryAnalytics.data?.providers.map((provider) => <span key={provider.provider_id} className="rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-700"><span className="font-semibold">{provider.provider_id}</span><span className="ml-2">{provider.succeeded}/{provider.total} succeeded · {provider.failed} failed</span></span>)}
            </div>
            {(deliveryAnalytics.data?.top_errors.length ?? 0) > 0 && <div className="mt-5 rounded-xl border border-rose-100 bg-rose-50/60 p-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-rose-900">Most common delivery errors</h3>
              <ul className="mt-2 flex flex-wrap gap-2">{deliveryAnalytics.data?.top_errors.map((item) => <li key={item.code} className="rounded-lg bg-white px-3 py-2 text-xs text-rose-900"><code>{item.code}</code><span className="ml-2 font-semibold">{item.count}</span></li>)}</ul>
            </div>}
          </>}
      </section>

      <section aria-labelledby="commerce-approval-title" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 id="commerce-approval-title" className="font-semibold">Commerce approval activity</h2><p className="mt-1 text-xs text-slate-500">Human review outcomes and time to review for order requests in the selected period.</p></div>
          <span className="rounded-lg bg-amber-50 p-2 text-amber-800"><ShieldCheck size={18} aria-hidden="true"/></span>
        </div>
        {commerceApprovals.isPending ? <p role="status" className="mt-5 text-sm text-slate-500">Loading approval metrics…</p>
          : commerceApprovals.isError ? <p role="alert" className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-800">Commerce approval metrics could not be loaded. Other analytics remain available.</p>
          : commerceApprovals.data?.total === 0 ? <p className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No commerce approval requests were recorded in this date range.</p>
          : <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
            <AutomationMetric label="Requests" value={commerceApprovals.data?.total.toLocaleString() ?? "0"}/>
            <AutomationMetric label="Pending" value={commerceApprovals.data?.pending.toLocaleString() ?? "0"} tone="blue"/>
            <AutomationMetric label="Approved" value={commerceApprovals.data?.approved.toLocaleString() ?? "0"} tone="green"/>
            <AutomationMetric label="Rejected" value={commerceApprovals.data?.rejected.toLocaleString() ?? "0"} tone={commerceApprovals.data?.rejected ? "red" : "neutral"}/>
            <AutomationMetric label="Expired / cancelled" value={((commerceApprovals.data?.expired ?? 0) + (commerceApprovals.data?.cancelled ?? 0)).toLocaleString()}/>
            <AutomationMetric label="Executed" value={commerceApprovals.data?.execution_succeeded.toLocaleString() ?? "0"} tone="green"/>
            <AutomationMetric label="Execution failed" value={commerceApprovals.data?.execution_failed.toLocaleString() ?? "0"} tone={commerceApprovals.data?.execution_failed ? "red" : "neutral"}/>
            <div className="col-span-2 rounded-xl bg-slate-50 p-3 sm:col-span-4 xl:col-span-7"><p className="text-xs font-medium text-slate-600">Average human review time</p><p className="mt-1 text-lg font-bold text-slate-950">{commerceApprovals.data?.average_review_seconds == null ? "No reviewed requests" : formatDuration(commerceApprovals.data.average_review_seconds)}</p><p className="mt-1 text-xs text-slate-500">Measured from request creation to an Owner/Admin approval or rejection.</p>
              {commerceApprovals.data?.median_review_seconds != null && (
                <p className="mt-2 text-xs text-slate-600">
                  Median {formatDuration(commerceApprovals.data.median_review_seconds)}
                  {commerceApprovals.data.reviewed_count != null && ` across ${commerceApprovals.data.reviewed_count.toLocaleString()} reviewed requests`}
                </p>
              )}</div>
            {commerceApprovals.data?.timed_execution_count != null && (
              <div className="col-span-2 rounded-xl bg-slate-50 p-3 sm:col-span-4 xl:col-span-7">
                <p className="text-xs font-medium text-slate-600">Average approval to execution completion</p>
                <p className="mt-1 text-lg font-bold text-slate-950">
                  {commerceApprovals.data.average_approval_to_completion_seconds == null
                    ? "No timed executions"
                    : formatDuration(commerceApprovals.data.average_approval_to_completion_seconds)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Includes queue time and retries across {commerceApprovals.data.timed_execution_count.toLocaleString()} completed executions.
                </p>
              </div>
            )}
          </div>}
        {!commerceApprovals.isError && commerceApprovals.data && commerceApprovals.data.total > 0 && (
          <CommerceApprovalTrend daily={commerceApprovals.data.daily} />
        )}
      </section>

      <section aria-labelledby="support-response-title" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 id="support-response-title" className="font-semibold">First response time</h2><p className="mt-1 text-xs text-slate-500">Time from the first customer message to the first teammate or AI reply. Outbound channel replies count when their delivery job succeeds. The date range follows the first customer message in UTC.</p></div>
          <span className="rounded-lg bg-blue-50 p-2 text-blue-700"><Activity size={18} aria-hidden="true"/></span>
        </div>
        {supportResponses.isPending ? <p role="status" className="mt-5 text-sm text-slate-500">Loading response-time metrics…</p>
          : supportResponses.isError ? <p role="alert" className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-800">Response-time metrics could not be loaded. Other analytics remain available.</p>
          : supportResponses.data?.conversations === 0 ? <p className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No customer conversations were recorded in this date range.</p>
          : <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <AutomationMetric label="Conversations" value={supportResponses.data?.conversations.toLocaleString() ?? "0"}/>
            <AutomationMetric label="Received a reply" value={`${supportResponses.data?.responded.toLocaleString() ?? "0"}${supportResponses.data?.conversations ? ` · ${Math.round((supportResponses.data.responded / supportResponses.data.conversations) * 100)}%` : ""}`} tone="green"/>
            <AutomationMetric label="Awaiting first reply" value={supportResponses.data?.awaiting_first_response.toLocaleString() ?? "0"} tone={(supportResponses.data?.awaiting_first_response ?? 0) > 0 ? "blue" : "neutral"}/>
            <AutomationMetric label="Average first response" value={supportResponses.data?.average_first_response_seconds == null ? "No replies yet" : formatDuration(supportResponses.data.average_first_response_seconds)}/>
            <AutomationMetric label="Median first response" value={supportResponses.data?.median_first_response_seconds == null ? "No replies yet" : formatDuration(supportResponses.data.median_first_response_seconds)}/>
            <AutomationMetric
              label="P95 first response"
              value={supportResponses.data?.p95_first_response_seconds == null
                ? "—"
                : formatDuration(supportResponses.data.p95_first_response_seconds)}
            />
          </div>}
        {!supportResponses.isError && supportResponses.data?.sla && supportResponses.data.sla.tickets > 0 && (
          <section className="mt-5 rounded-xl border border-slate-200 bg-slate-50/70 p-4" aria-labelledby="first-response-sla-title">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 id="first-response-sla-title" className="text-sm font-semibold text-slate-800">First-response SLA · ticket level</h3>
              <p className="text-xs text-slate-500">Compliance is met ÷ replied; open overdue and at-risk tickets are counted separately.</p>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
              <AutomationMetric label="Compliance" value={supportResponses.data.sla.compliance_rate == null ? "—" : `${supportResponses.data.sla.compliance_rate}%`} tone="green"/>
              <AutomationMetric label="Met" value={supportResponses.data.sla.met.toLocaleString()} tone="green"/>
              <AutomationMetric label="Breached" value={supportResponses.data.sla.breached.toLocaleString()} tone={supportResponses.data.sla.breached > 0 ? "blue" : "neutral"}/>
              <AutomationMetric label="Overdue" value={supportResponses.data.sla.overdue.toLocaleString()} tone={supportResponses.data.sla.overdue > 0 ? "blue" : "neutral"}/>
              <AutomationMetric label="At risk" value={supportResponses.data.sla.at_risk.toLocaleString()} tone={supportResponses.data.sla.at_risk > 0 ? "blue" : "neutral"}/>
              <AutomationMetric label="On track" value={supportResponses.data.sla.on_track.toLocaleString()}/>
              <AutomationMetric label="Awaiting" value={supportResponses.data.sla.awaiting.toLocaleString()}/>
            </div>
          </section>
        )}
        {!supportResponses.isError && supportResponses.data?.longest_unanswered_seconds != null && (
          <p className="mt-4 text-xs text-slate-600">
            Longest current wait in this range{" "}
            <span className="font-semibold">{formatDuration(supportResponses.data.longest_unanswered_seconds)}</span>
          </p>
        )}
        {!supportResponses.isError && (supportResponses.data?.by_channel.length ?? 0) > 0 && (
          <div className="mt-5 overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full min-w-[680px] text-left text-sm">
              <caption className="px-3 py-2 text-left text-xs text-slate-500">
                First response by conversation channel for the selected date range.
              </caption>
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th scope="col" className="px-3 py-2">Channel</th>
                  <th scope="col" className="px-3 py-2">Conversations</th>
                  <th scope="col" className="px-3 py-2">Replied</th>
                  <th scope="col" className="px-3 py-2">Awaiting</th>
                  <th scope="col" className="px-3 py-2">Average</th>
                  <th scope="col" className="px-3 py-2">P95</th>
                  <th scope="col" className="px-3 py-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {supportResponses.data?.by_channel.map((channel) => (
                  <tr key={channel.channel} className="border-t border-slate-100">
                    <th scope="row" className="px-3 py-2.5 font-semibold capitalize text-slate-800">
                      {channel.channel.replaceAll("_", " ")}
                    </th>
                    <td className="px-3 py-2.5 tabular-nums">{channel.conversations.toLocaleString()}</td>
                    <td className="px-3 py-2.5 tabular-nums text-emerald-800">{channel.responded.toLocaleString()}</td>
                    <td className="px-3 py-2.5 tabular-nums">{channel.awaiting_first_response.toLocaleString()}</td>
                    <td className="px-3 py-2.5 tabular-nums">{channel.average_first_response_seconds == null ? "—" : formatDuration(channel.average_first_response_seconds)}</td>
                    <td className="px-3 py-2.5 tabular-nums">{channel.p95_first_response_seconds == null ? "—" : formatDuration(channel.p95_first_response_seconds)}</td>
                    <td className="px-3 py-2.5"><Link href={`/dashboard/inbox?channel=${encodeURIComponent(channel.channel)}`} className="font-semibold text-blue-700 underline-offset-4 hover:underline">View inbox</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm font-semibold">
          {([
            ["breached", "View breached"], ["overdue", "View overdue"], ["at_risk", "View at risk"],
          ] as const).map(([status, label]) => (
            <Link key={status} href={`/dashboard/inbox?sla_status=${status}`} className="text-blue-700 underline-offset-4 hover:underline">
              {label} first replies in Inbox
            </Link>
          ))}
        </div>
        {supportResponses.data && supportResponses.data.daily.length > 0 && <SupportResponseTrend daily={supportResponses.data.daily}/>}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6" aria-labelledby="usage-title">
          <div className="flex items-start justify-between"><div><h2 id="usage-title" className="font-semibold">Daily token usage</h2><p className="mt-1 text-xs text-slate-500">Prompt and completion tokens per day</p></div><span className="rounded-lg bg-blue-50 p-2 text-blue-700"><BarChart3 size={18}/></span></div>
          {!usage.data ? <p className="py-12 text-center text-sm text-slate-500">{usage.isPending ? "Loading AI usage…" : "AI usage unavailable."}</p> : usage.data.executions === 0 ? <p className="py-12 text-center text-sm text-slate-500">No AI activity in this date range.</p> : <div className="mt-6 flex h-48 items-end gap-1 overflow-x-auto border-b border-slate-100 pb-2" role="img" aria-label="Daily AI token usage chart">{usage.data?.daily.map((point) => { const total = point.prompt_tokens + point.completion_tokens; const height = Math.max(3, Math.round((total / maxDaily) * 100)); return <div key={point.date} title={`${point.date}: ${total.toLocaleString()} tokens`} className="flex min-w-2 flex-1 flex-col justify-end"><div className="rounded-t-sm bg-blue-500" style={{ height: `${height}%` }}/><span className="sr-only">{point.date}: {total} tokens</span></div>; })}</div>}
          {usage.data && usage.data.executions !== 0 && <div className="mt-2 flex justify-between text-[11px] text-slate-400"><span>{usage.data?.start_date}</span><span>{usage.data?.end_date}</span></div>}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6" aria-labelledby="eval-title">
          <h2 id="eval-title" className="font-semibold">Draft evaluations</h2><p className="mt-1 text-xs text-slate-500">Feedback is tied to a completed AI draft and your teammate account.</p>
          <div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-xl bg-emerald-50 p-3"><p className="text-xs font-medium text-emerald-800">Helpful</p><p className="mt-1 text-xl font-bold text-emerald-950">{evaluations.data?.helpful ?? (evaluations.isPending ? "Loading…" : "Unavailable")}</p></div><div className="rounded-xl bg-rose-50 p-3"><p className="text-xs font-medium text-rose-800">Needs work</p><p className="mt-1 text-xl font-bold text-rose-950">{evaluations.data?.not_helpful ?? (evaluations.isPending ? "Loading…" : "Unavailable")}</p></div></div>
          {executions.isPending ? <p role="status" className="mt-5 text-sm">Loading completed drafts…</p>
            : executions.isError ? <p role="alert" className="mt-5 text-sm text-red-700">Completed drafts could not be loaded.</p>
            : eligible.length === 0 ? <p className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">Completed reply drafts will appear here for evaluation.</p> : <form className="mt-5 space-y-3" onSubmit={(event) => { event.preventDefault(); if (executionId) evaluate.mutate(); }}>
            <label className="block text-xs font-semibold text-slate-600">Completed draft<Select aria-label="Completed draft to evaluate" value={executionId} onChange={(event) => setExecutionId(event.target.value)} className="mt-1"><option value="">Select a draft</option>{eligible.map((item) => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} · {item.safe_summary ?? "Reply draft"}</option>)}</Select></label>
            <label className="block text-xs font-semibold text-slate-600">Feedback category<Select aria-label="Evaluation category" value={category ?? ""} onChange={(event) => setCategory((event.target.value || undefined) as AIEvaluationCreate["category"])} className="mt-1"><option value="">No category</option><option value="accuracy">Accuracy</option><option value="grounding">Grounding</option><option value="relevance">Relevance</option><option value="tone">Tone</option></Select></label>
            <div className="grid grid-cols-2 gap-2"><Button type="button" variant={rating === "helpful" ? "primary" : "secondary"} aria-pressed={rating === "helpful"} onClick={() => setRating("helpful")}><ThumbsUp size={15}/>Helpful</Button><Button type="button" variant={rating === "not_helpful" ? "primary" : "secondary"} aria-pressed={rating === "not_helpful"} onClick={() => setRating("not_helpful")}><ThumbsDown size={15}/>Needs work</Button></div>
            <Button type="submit" disabled={!executionId || evaluate.isPending} className="w-full">{evaluate.isPending ? "Saving feedback…" : "Save evaluation"}</Button>
            {evaluate.isError && <p role="alert" className="text-sm text-red-700">Feedback could not be saved.</p>}{evaluate.isSuccess && <p role="status" className="text-sm text-emerald-700">Evaluation saved.</p>}
          </form>}
        </section>
      </div>
      <RecommendationInsights data={recommendations.data} loading={recommendations.isPending} error={recommendations.isError}/>
    </>}
  </div>;
}

function CommerceApprovalTrend({ daily }: { daily: CommerceApprovalAnalytics["daily"] }) {
  const activeDays = daily.filter((day) => day.total > 0);
  if (!activeDays.length) return null;

  return (
    <details className="mt-5 rounded-xl border border-slate-200 p-3">
      <summary className="cursor-pointer rounded text-sm font-semibold focus-visible:outline-2">
        Daily commerce request outcomes
      </summary>
      <div className="mt-3 max-h-72 overflow-auto">
        <table className="w-full whitespace-nowrap text-right text-xs tabular-nums">
          <caption className="pb-2 text-left text-slate-500">
            Current outcomes by request creation date in UTC. Dates with no requests are omitted.
          </caption>
          <thead>
            <tr>
              <th scope="col" className="p-2 text-left">Date</th>
              {["Total", "Pending", "Approved", "Rejected", "Expired", "Cancelled"].map((label) => (
                <th key={label} scope="col" className="p-2">{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {activeDays.map((day) => (
              <tr key={day.date} className="border-t border-slate-100">
                <th scope="row" className="p-2 text-left font-medium"><time dateTime={day.date}>{day.date}</time></th>
                {[day.total, day.pending, day.approved, day.rejected, day.expired, day.cancelled].map((count, index) => (
                  <td key={index} className="p-2">{count.toLocaleString()}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function formatDuration(seconds: number) {
  if (seconds < 60) return `${Math.round(seconds)} sec`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  const hours = seconds / 3600;
  return hours >= 24 ? `${(hours / 24).toFixed(1)} days` : `${hours.toFixed(1)} hours`;
}

function AutomationMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "green" | "blue" | "red" }) {
  const toneClass = {
    neutral: "bg-slate-50 text-slate-950",
    green: "bg-emerald-50 text-emerald-950",
    blue: "bg-blue-50 text-blue-950",
    red: "bg-rose-50 text-rose-950",
  }[tone];
  return <div className={`min-w-0 rounded-xl p-3 ${toneClass}`}><p className="text-xs font-medium opacity-70">{label}</p><p className="mt-1 truncate text-lg font-bold">{value}</p></div>;
}

function AutomationTrend({ daily, topErrors }: { daily: AutomationMetrics["daily"]; topErrors: AutomationMetrics["top_errors"] }) {
  const peak = Math.max(1, ...daily.map((point) => point.total));
  return <div className="mt-6 border-t border-slate-100 pt-5">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><h3 className="text-sm font-semibold">Daily workflow outcomes</h3><p className="mt-1 text-xs text-slate-500">Runs grouped by UTC creation date</p></div>
      <ul aria-label="Chart legend" className="flex gap-3 text-xs text-slate-600"><li className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-emerald-500"/>Succeeded</li><li className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-rose-500"/>Failed</li><li className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-slate-300"/>Other</li></ul>
    </div>
    <div className="mt-4 flex h-36 items-end gap-1 overflow-x-auto border-b border-slate-100 pb-2" role="img" aria-label="Daily workflow runs grouped by outcome">
      {daily.map((point) => {
        const other = point.total - point.succeeded - point.failed;
        const barHeight = Math.max(point.total ? 4 : 1, Math.round((point.total / peak) * 100));
        const successHeight = point.total ? Math.round((point.succeeded / point.total) * barHeight) : 0;
        const failedHeight = point.total ? Math.round((point.failed / point.total) * barHeight) : 0;
        const otherHeight = Math.max(point.total ? 1 : 0, barHeight - successHeight - failedHeight);
        return <div key={point.date} title={`${point.date}: ${point.total} runs, ${point.succeeded} succeeded, ${point.failed} failed`} className="flex min-w-2 flex-1 flex-col justify-end">
          <div className="flex flex-col justify-end overflow-hidden rounded-t-sm" style={{ height: `${barHeight}%` }}>
            {successHeight > 0 && <span className="bg-emerald-500" style={{ height: `${successHeight}px` }} />}
            {failedHeight > 0 && <span className="bg-rose-500" style={{ height: `${failedHeight}px` }} />}
            {other > 0 && <span className="bg-slate-300" style={{ height: `${otherHeight}px` }} />}
          </div><span className="sr-only">{point.date}: {point.total} runs, {point.succeeded} succeeded, {point.failed} failed, {other} other.</span>
        </div>;
      })}
    </div>
    <div className="mt-2 flex justify-between text-[11px] text-slate-400"><span>{daily[0]?.date}</span><span>{daily.at(-1)?.date}</span></div>
    {topErrors.length > 0 && <div className="mt-5 rounded-xl border border-rose-100 bg-rose-50/60 p-4">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-rose-900">Most common workflow errors</h4>
      <ul className="mt-2 flex flex-wrap gap-2">{topErrors.map((item) => <li key={item.code} className="rounded-lg bg-white px-3 py-2 text-xs text-rose-900"><code>{item.code}</code><span className="ml-2 font-semibold">{item.count}</span></li>)}</ul>
    </div>}
  </div>;
}

function SupportResponseTrend({ daily }: { daily: import("../api/analytics-api").SupportResponseAnalytics["daily"] }) {
  const peak = Math.max(1, ...daily.map((point) => point.average_first_response_seconds ?? 0));
  return <div className="mt-5 border-t border-slate-100 pt-4">
    <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">Daily average response time</h3><span className="text-xs text-slate-500">UTC first customer message date</span></div>
    <div className="mt-3 flex h-24 items-end gap-1 overflow-x-auto border-b border-slate-100 pb-2" role="img" aria-label="Daily average first response time">
      {daily.map((point) => {
        const seconds = point.average_first_response_seconds ?? 0;
        const height = seconds ? Math.max(4, Math.round((seconds / peak) * 100)) : 1;
        return <div key={point.date} title={`${point.date}: ${seconds ? formatDuration(seconds) : "no replies"} · ${point.responded}/${point.conversations} replied`} className="flex min-w-2 flex-1 flex-col justify-end">
          <span className="rounded-t-sm bg-blue-500" style={{ height: `${height}%` }}/>
          <span className="sr-only">{point.date}: {seconds ? formatDuration(seconds) : "no replies"}; {point.responded} of {point.conversations} conversations replied.</span>
        </div>;
      })}
    </div>
    <div className="mt-2 flex justify-between text-[11px] text-slate-400"><span>{daily[0]?.date}</span><span>{daily.at(-1)?.date}</span></div>
  </div>;
}

function RecommendationInsights({ data, loading, error }: { data: import("@/features/recommendations/api/recommendation-api").RecommendationAnalytics | undefined; loading: boolean; error: boolean }) {
  const trends = data?.trends ?? [];
  const recommended = data?.top_recommended_products ?? [];
  const clicked = data?.top_clicked_products ?? [];
  const noResults = data?.no_result_categories ?? [];
  const errorCodes = data?.error_codes ?? [];
  const max = Math.max(1, ...trends.map((point) => point.impressions));
  return <section aria-labelledby="recommendation-analytics-title" className="space-y-4">
    <div><p className="text-xs font-bold uppercase tracking-[.16em] text-violet-700">Commerce intelligence</p><h2 id="recommendation-analytics-title" className="mt-1 text-xl font-bold">Product recommendations</h2><p className="mt-1 text-sm text-slate-500">Tenant-scoped storefront events and recommendation execution health.</p></div>
    {loading ? <div role="status" className="h-40 animate-pulse rounded-2xl bg-slate-100"/> : error ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">Recommendation analytics could not be loaded.</div> : data && <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric title="Impressions" value={data.impressions.toLocaleString()} detail="Recommendation products rendered" icon={<Sparkles size={18}/>}/>
        <Metric title="Product clicks" value={data.product_clicks.toLocaleString()} detail={`${data.impressions ? Math.round((data.product_clicks / data.impressions) * 100) : 0}% of impressions`} icon={<BarChart3 size={18}/>}/>
        <Metric title="Comparisons" value={data.comparisons.toLocaleString()} detail={`${data.rejected_recommendations} rejected · ${data.no_result_searches} no-result`} icon={<ThumbsDown size={18}/>}/>
        <Metric title="Recommendation AI cost" value={data.estimated_cost_usd == null ? "Not configured" : `$${data.estimated_cost_usd.toFixed(4)}`} detail={`${data.prompt_tokens + data.completion_tokens} tokens · ${data.failed_executions} failed`} icon={<CircleDollarSign size={18}/>}/>
      </div>
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white" aria-labelledby="recommendation-bot-performance-title">
        <div className="border-b border-slate-100 p-4"><h3 id="recommendation-bot-performance-title" className="font-semibold">Performance by AI bot</h3><p className="mt-1 text-xs text-slate-500">Counts are attributed through the persisted widget execution that handled each recommendation.</p></div>
        {data.bots.length ? <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead className="bg-slate-50 text-xs text-slate-500"><tr><th scope="col" className="px-4 py-2.5">Bot</th><th scope="col" className="px-4 py-2.5">Shown</th><th scope="col" className="px-4 py-2.5">Clicks</th><th scope="col" className="px-4 py-2.5">Comparisons</th><th scope="col" className="px-4 py-2.5">No results</th><th scope="col" className="px-4 py-2.5">Handoffs</th></tr></thead><tbody>{data.bots.map((bot) => <tr key={bot.bot_id} className="border-t border-slate-100"><th scope="row" className="px-4 py-3 font-semibold text-slate-800">{bot.bot_name}</th><td className="px-4 py-3 tabular-nums">{bot.impressions.toLocaleString()}</td><td className="px-4 py-3 tabular-nums">{bot.product_clicks.toLocaleString()}</td><td className="px-4 py-3 tabular-nums">{bot.comparisons.toLocaleString()}</td><td className="px-4 py-3 tabular-nums">{bot.no_results.toLocaleString()}</td><td className="px-4 py-3 tabular-nums">{bot.human_handoffs.toLocaleString()}</td></tr>)}</tbody></table></div> : <p className="p-4 text-sm text-slate-500">No bot-attributed recommendation events in this date range.</p>}
      </section>
      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5" aria-label="Recommendation trend"><h3 className="font-semibold">Recommendation funnel and trend</h3><p className="mt-1 text-xs text-slate-500">Daily product impressions and clicks. Mean generation time: {data.average_latency_ms == null ? "no completed samples" : `${data.average_latency_ms} ms`}.</p>
          <div className="mt-4 grid grid-cols-5 gap-2 text-center text-xs"><Funnel label="Shown" count={data.impressions}/><Funnel label="Clicked" count={data.product_clicks}/><Funnel label="Compared" count={data.comparisons}/><Funnel label="No result" count={data.no_result_searches}/><Funnel label="Handoff" count={data.human_handoffs}/></div>
          <div className="mt-5 flex h-36 items-end gap-1 overflow-x-auto border-b border-slate-100 pb-2" role="img" aria-label="Daily recommendation impression volume">{trends.map((point) => <div key={point.date} title={`${point.date}: ${point.impressions} impressions, ${point.clicks} clicks`} className="flex min-w-2 flex-1 flex-col justify-end"><div className="rounded-t-sm bg-violet-500" style={{ height: `${Math.max(point.impressions ? 4 : 1, Math.round(point.impressions / max * 100))}%` }}/><div className="mt-0.5 rounded-t-sm bg-blue-400" style={{ height: `${Math.max(point.clicks ? 3 : 1, Math.round(point.clicks / max * 100))}%` }}/></div>)}</div>
          <p className="mt-2 text-xs text-slate-500">Purchases and cart adds are unavailable until a trusted commerce event source is configured. Attribution window planned: {data.attribution_window_days} days; no conversion is currently attributed.</p>
        </section>
        <div className="space-y-5"><LeaderList title="Top recommended" items={recommended.map((item) => ({ product_id: String(item.product_id), title: String(item.title), count: Number(item.count) }))}/><LeaderList title="Top clicked" items={clicked.map((item) => ({ product_id: String(item.product_id), title: String(item.title), count: Number(item.count) }))}/><LeaderList title="No-result categories" items={noResults.map((item) => ({ product_id: String(item.category), title: String(item.category), count: Number(item.count) }))}/><LeaderList title="AI errors" items={errorCodes.map((item) => ({ product_id: String(item.code), title: String(item.code), count: Number(item.count) }))}/></div>
      </div>
    </>}
  </section>;
}

function Funnel({ label, count }: { label: string; count: number }) { return <div className="rounded-lg bg-slate-50 p-2"><p className="text-lg font-bold text-slate-900">{count.toLocaleString()}</p><p className="mt-0.5 text-slate-500">{label}</p></div>; }
function LeaderList({ title, items }: { title: string; items: { product_id: string; title: string; count: number }[] }) { return <section className="rounded-2xl border border-slate-200 bg-white p-5"><h3 className="font-semibold">{title}</h3>{items.length ? <ol className="mt-3 space-y-2">{items.slice(0, 5).map((item, index) => <li key={`${item.product_id}-${index}`} className="flex items-center justify-between gap-3 text-sm"><span className="truncate text-slate-700">{item.title}</span><span className="shrink-0 rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold">{item.count}</span></li>)}</ol> : <p className="mt-3 text-sm text-slate-500">No activity in this date range.</p>}</section>; }

function Metric({ title, value, detail, icon, available = true, loading = false }: { title: string; value: string; detail: string; icon: React.ReactNode; available?: boolean; loading?: boolean }) {
  return <article className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between text-[var(--text-muted)]"><p className="helper-text font-medium">{title}</p>{icon}</div><p className="kpi-value mt-3 truncate">{available ? value : loading ? "Loading…" : "Unavailable"}</p><p className="meta-text mt-1">{available ? detail : loading ? "Fetching metrics" : "Metrics could not be loaded"}</p></article>;
}
