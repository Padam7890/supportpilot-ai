"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, CircleDollarSign, LoaderCircle, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { listAIExecutions } from "@/features/ai/api/ai-api";
import {
  analyticsQueryKeys,
  getAIUsage,
  getEvaluationSummary,
  submitEvaluation,
  type AIEvaluationCreate,
} from "../api/analytics-api";

function dateValue(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
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
  const queryClient = useQueryClient();
  const usage = useQuery({
    queryKey: analyticsQueryKeys.usage(startDate, endDate),
    queryFn: () => getAIUsage(startDate, endDate),
    enabled: startDate <= endDate,
  });
  const evaluations = useQuery({
    queryKey: analyticsQueryKeys.evaluations(startDate, endDate),
    queryFn: () => getEvaluationSummary(startDate, endDate),
    enabled: startDate <= endDate,
  });
  const executions = useQuery({ queryKey: ["ai-executions", "analytics"], queryFn: () => listAIExecutions(100, 0) });
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
      <div><p className="text-xs font-bold uppercase tracking-[.16em] text-blue-700">Workspace insights</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Analytics</h1><p className="mt-2 text-sm text-slate-500">AI usage and teammate feedback from real workspace activity.</p></div>
      <div className="flex flex-wrap items-end gap-3"><label className="text-xs font-semibold text-slate-600">From<input aria-label="Analytics start date" type="date" value={startDate} max={endDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"/></label><label className="text-xs font-semibold text-slate-600">To<input aria-label="Analytics end date" type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)} className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"/></label></div>
    </header>

    {(usage.isError || evaluations.isError) && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">Analytics could not be loaded. Refresh the page or adjust the selected date range.</div>}
    {usage.isPending || evaluations.isPending ? <div role="status" className="flex items-center gap-2 rounded-xl bg-white p-8 text-sm text-slate-500"><LoaderCircle className="animate-spin" size={17}/>Loading analytics…</div> : <>
      <section aria-label="AI usage summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric title="AI requests" value={usage.data?.executions.toLocaleString() ?? "0"} detail={`${usage.data?.succeeded ?? 0} completed · ${usage.data?.failed ?? 0} failed`} icon={<Sparkles size={18}/>} />
        <Metric title="Tokens used" value={usage.data?.total_tokens.toLocaleString() ?? "0"} detail={`${usage.data?.prompt_tokens.toLocaleString() ?? "0"} input · ${usage.data?.completion_tokens.toLocaleString() ?? "0"} output`} icon={<BarChart3 size={18}/>} />
        <Metric title="Estimated AI cost" value={usage.data?.estimated_cost_usd == null ? "Not configured" : `$${usage.data.estimated_cost_usd.toFixed(4)}`} detail={usage.data?.estimated_cost_usd == null ? "Set provider token rates to estimate cost" : "Based on configured input and output rates"} icon={<CircleDollarSign size={18}/>} />
        <Metric title="Helpful feedback" value={evaluations.data?.helpful_rate == null ? "No ratings" : `${Math.round(evaluations.data.helpful_rate * 100)}%`} detail={`${evaluations.data?.rated ?? 0} teammate ratings`} icon={<ThumbsUp size={18}/>} />
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6" aria-labelledby="usage-title">
          <div className="flex items-start justify-between"><div><h2 id="usage-title" className="font-semibold">Daily token usage</h2><p className="mt-1 text-xs text-slate-500">Prompt and completion tokens per day</p></div><span className="rounded-lg bg-blue-50 p-2 text-blue-700"><BarChart3 size={18}/></span></div>
          {usage.data?.executions === 0 ? <p className="py-12 text-center text-sm text-slate-500">No AI activity in this date range.</p> : <div className="mt-6 flex h-48 items-end gap-1 overflow-x-auto border-b border-slate-100 pb-2" role="img" aria-label="Daily AI token usage chart">{usage.data?.daily.map((point) => { const total = point.prompt_tokens + point.completion_tokens; const height = Math.max(3, Math.round((total / maxDaily) * 100)); return <div key={point.date} title={`${point.date}: ${total.toLocaleString()} tokens`} className="flex min-w-2 flex-1 flex-col justify-end"><div className="rounded-t-sm bg-blue-500" style={{ height: `${height}%` }}/><span className="sr-only">{point.date}: {total} tokens</span></div>; })}</div>}
          {usage.data?.executions !== 0 && <div className="mt-2 flex justify-between text-[11px] text-slate-400"><span>{usage.data?.start_date}</span><span>{usage.data?.end_date}</span></div>}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6" aria-labelledby="eval-title">
          <h2 id="eval-title" className="font-semibold">Draft evaluations</h2><p className="mt-1 text-xs text-slate-500">Feedback is tied to a completed AI draft and your teammate account.</p>
          <div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-xl bg-emerald-50 p-3"><p className="text-xs font-medium text-emerald-800">Helpful</p><p className="mt-1 text-xl font-bold text-emerald-950">{evaluations.data?.helpful ?? 0}</p></div><div className="rounded-xl bg-rose-50 p-3"><p className="text-xs font-medium text-rose-800">Needs work</p><p className="mt-1 text-xl font-bold text-rose-950">{evaluations.data?.not_helpful ?? 0}</p></div></div>
          {eligible.length === 0 ? <p className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">Completed reply drafts will appear here for evaluation.</p> : <form className="mt-5 space-y-3" onSubmit={(event) => { event.preventDefault(); if (executionId) evaluate.mutate(); }}>
            <label className="block text-xs font-semibold text-slate-600">Completed draft<Select aria-label="Completed draft to evaluate" value={executionId} onChange={(event) => setExecutionId(event.target.value)} className="mt-1"><option value="">Select a draft</option>{eligible.map((item) => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} · {item.safe_summary ?? "Reply draft"}</option>)}</Select></label>
            <label className="block text-xs font-semibold text-slate-600">Feedback category<Select aria-label="Evaluation category" value={category ?? ""} onChange={(event) => setCategory((event.target.value || undefined) as AIEvaluationCreate["category"])} className="mt-1"><option value="">No category</option><option value="accuracy">Accuracy</option><option value="grounding">Grounding</option><option value="relevance">Relevance</option><option value="tone">Tone</option></Select></label>
            <div className="grid grid-cols-2 gap-2"><Button type="button" variant={rating === "helpful" ? "primary" : "secondary"} aria-pressed={rating === "helpful"} onClick={() => setRating("helpful")}><ThumbsUp size={15}/>Helpful</Button><Button type="button" variant={rating === "not_helpful" ? "primary" : "secondary"} aria-pressed={rating === "not_helpful"} onClick={() => setRating("not_helpful")}><ThumbsDown size={15}/>Needs work</Button></div>
            <Button type="submit" disabled={!executionId || evaluate.isPending} className="w-full">{evaluate.isPending ? "Saving feedback…" : "Save evaluation"}</Button>
            {evaluate.isError && <p role="alert" className="text-sm text-red-700">Feedback could not be saved.</p>}{evaluate.isSuccess && <p role="status" className="text-sm text-emerald-700">Evaluation saved.</p>}
          </form>}
        </section>
      </div>
    </>}
  </div>;
}

function Metric({ title, value, detail, icon }: { title: string; value: string; detail: string; icon: React.ReactNode }) {
  return <article className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between text-slate-500"><p className="text-sm font-medium">{title}</p>{icon}</div><p className="mt-3 truncate text-2xl font-bold tracking-tight text-slate-950">{value}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></article>;
}
