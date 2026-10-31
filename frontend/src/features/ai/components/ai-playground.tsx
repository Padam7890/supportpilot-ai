"use client";

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { BookOpen, Clipboard, LoaderCircle, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { aiQueryKeys, createPlaygroundExecution, getAIExecution } from "../api/ai-api";
import { playgroundSchema } from "../schemas/ai.schema";

type PlaygroundValues = z.infer<typeof playgroundSchema>;

export function AIPlayground() {
  const [executionId, setExecutionId] = useState<string>();
  const [copied, setCopied] = useState(false);
  const user = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const form = useForm<PlaygroundValues>({
    resolver: zodResolver(playgroundSchema),
    defaultValues: { question: "" },
    mode: "onChange",
  });
  const run = useMutation({
    mutationFn: createPlaygroundExecution,
    onSuccess: (execution) => {
      setExecutionId(execution.id);
      setCopied(false);
    },
  });
  const execution = useQuery({
    queryKey: aiQueryKeys.execution(executionId),
    queryFn: () => getAIExecution(executionId!),
    enabled: Boolean(executionId),
    refetchInterval: (query) => {
      const active = ["queued", "running"].includes(query.state.data?.status ?? "");
      return active && typeof document !== "undefined" && document.visibilityState === "visible" ? 1500 : false;
    },
    refetchIntervalInBackground: false,
  });
  const canRun = ["owner", "admin", "agent"].includes(user.data?.role ?? "");
  const busy = run.isPending || execution.data?.status === "queued" || execution.data?.status === "running";

  async function copyDraft() {
    const draft = execution.data?.draft;
    if (!draft) return;
    await navigator.clipboard.writeText(draft);
    setCopied(true);
  }

  return <div className="space-y-6">
    <header>
      <p className="flex items-center gap-2 text-sm font-semibold text-blue-700"><Sparkles size={16}/> AI assistance</p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-950">AI playground</h1>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Ask a question against your approved knowledge sources. Results are suggestions for your team; the assistant never sends a customer message.</p>
    </header>

    {!canRun && user.data && <p role="status" className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">Your role has read-only access to AI executions.</p>}
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
      <Panel>
        <PanelHeader title="Ask your knowledge base" description="The model receives only this question and matching tenant documents." action={<BookOpen size={17} className="text-slate-400"/>}/>
        <PanelBody>
          <form className="space-y-4" onSubmit={form.handleSubmit((values) => { setExecutionId(undefined); run.mutate(values); })}>
            <div>
              <label htmlFor="ai-playground-question" className="mb-1.5 block text-sm font-medium text-slate-700">Question</label>
              <Textarea id="ai-playground-question" placeholder="What is our return policy for an unused product?" className="min-h-36" disabled={!canRun || busy} aria-invalid={Boolean(form.formState.errors.question)} {...form.register("question")}/>
              {form.formState.errors.question && <p role="alert" className="mt-1 text-sm text-red-700">{form.formState.errors.question.message}</p>}
            </div>
            <Button type="submit" disabled={!canRun || busy}>
              {busy ? <><LoaderCircle size={16} className="animate-spin"/>Working…</> : <><Sparkles size={16}/>Generate answer</>}
            </Button>
          </form>
          {run.isError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{run.error.message}</p>}
          {execution.isError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">The execution status could not be refreshed. Try reloading this page.</p>}
        </PanelBody>
      </Panel>

      <Panel aria-live="polite">
        <PanelHeader title="Result" description={execution.data?.safe_summary ?? "The generated answer and its sources appear here."}/>
        <PanelBody>
          {!executionId && <p className="text-sm text-slate-500">Ask a question to create a grounded answer.</p>}
          {executionId && execution.isPending && <div className="space-y-3"><div className="h-4 w-2/3 animate-pulse rounded bg-slate-100"/><div className="h-24 animate-pulse rounded-xl bg-slate-100"/></div>}
          {execution.data && ["queued", "running"].includes(execution.data.status) && <p role="status" className="flex items-center gap-2 text-sm text-slate-600"><LoaderCircle size={16} className="animate-spin"/>The assistant is checking relevant documents…</p>}
          {execution.data?.status === "failed" && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">The AI request could not be completed. You can retry it.</p>}
          {execution.data?.status === "succeeded" && <>
            <div className="whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-800">{execution.data.draft}</div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500"><span>Draft only · {execution.data.usage.total_tokens ?? 0} tokens</span><Button size="sm" variant="secondary" onClick={copyDraft}><Clipboard size={14}/>{copied ? "Copied" : "Copy answer"}</Button></div>
            {execution.data.citations.length > 0 ? <section className="mt-5" aria-label="Sources"><h2 className="text-sm font-semibold text-slate-800">Sources</h2><ul className="mt-2 space-y-2">{execution.data.citations.map((citation) => <li key={`${citation.document_id}-${citation.chunk_index}`} className="rounded-xl border border-slate-200 p-3"><p className="text-xs font-semibold text-blue-700">{citation.document_name} · section {citation.chunk_index + 1}</p><p className="mt-1 text-sm leading-5 text-slate-600">{citation.excerpt}</p></li>)}</ul></section> : <p className="mt-4 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">No matching knowledge sources were found. Verify the answer before using it.</p>}
          </>}
        </PanelBody>
      </Panel>
    </div>
  </div>;
}
