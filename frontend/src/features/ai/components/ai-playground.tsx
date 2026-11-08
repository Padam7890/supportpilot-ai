"use client";

import { Select } from "@/components/ui";
import { SupportTraceLink } from "@/components/support-trace-link";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { BookOpen, Clipboard, LoaderCircle, RotateCcw, Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { aiQueryKeys, createPlaygroundExecution, getAIExecution, previewPlaygroundRetrieval, type AIPlaygroundRequest } from "../api/ai-api";
import { aiAgentsKey, listAIAgents } from "../api/ai-agent-api";
import { knowledgeBaseKey, listKnowledgeBases } from "@/features/knowledge/api/knowledge-base-api";
import { playgroundSchema } from "../schemas/ai.schema";

type PlaygroundValues = z.infer<typeof playgroundSchema>;

function failureMessage(errorCode: string | null | undefined) {
  if (errorCode === "provider_not_configured") return "The AI provider is not configured for this workspace.";
  if (errorCode === "provider_url_invalid") return "The AI provider URL is invalid. Check the server configuration.";
  if (errorCode === "provider_empty_response") return "The AI provider returned no answer. Try again.";
  if (errorCode === "provider_invalid_response") return "The AI provider returned an unreadable response. Check the configured provider endpoint and API compatibility.";
  if (errorCode === "provider_timeout") return "The AI provider took too long to respond. Check its availability, then retry.";
  if (errorCode === "provider_unreachable") return "The backend could not reach the AI provider. Check the provider URL and backend network access.";
  if (errorCode === "provider_http_401" || errorCode === "provider_http_403") return "The AI provider rejected its server credentials or access. Check the backend AI configuration.";
  if (errorCode === "provider_http_429") return "The AI provider rate limit or usage quota was reached. Check its usage and billing.";
  if (errorCode === "provider_http_400") return "The AI provider rejected the request parameters. Check the configured model and API compatibility.";
  if (errorCode?.startsWith("provider_http_5")) return "The AI provider is temporarily unavailable. Try again shortly.";
  if (errorCode === "ai_execution_failed") return "AI generation failed in the backend workflow (often a checkpoint/database or provider setup issue). Check the backend worker log at the request time, then retry.";
  if (errorCode === "worker_lease_expired") return "The AI worker did not finish this request. Check that the background worker is running, then retry.";
  return errorCode
    ? `The AI request failed (${errorCode}). Check the backend worker log at the request time, then retry.`
    : "The AI request could not be completed. Check the backend worker log at the request time, then retry.";
}

export function AIPlayground() {
  const [executionId, setExecutionId] = useState<string>();
  const [conversation, setConversation] = useState<Array<{ role: "user" | "assistant"; content: string }>>([]);
  const [pendingQuestion, setPendingQuestion] = useState<string>();
  const [copied, setCopied] = useState(false);
  const appendedExecutionId = useRef<string | undefined>(undefined);
  const lastRequest = useRef<AIPlaygroundRequest | undefined>(undefined);
  const user = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const agents = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents });
  const bases = useQuery({ queryKey: knowledgeBaseKey, queryFn: listKnowledgeBases });
  const form = useForm<PlaygroundValues>({
    resolver: zodResolver(playgroundSchema),
    defaultValues: { question: "", ai_agent_id: undefined },
    mode: "onChange",
  });
  useEffect(() => {
    const requestedAgentId = new URLSearchParams(window.location.search).get("ai_agent_id");
    const requestedAgent = requestedAgentId
      ? agents.data?.items.find((agent) => agent.id === requestedAgentId && agent.status === "active")
      : undefined;
    if (requestedAgent) {
      form.setValue("ai_agent_id", requestedAgent.id, { shouldDirty: false });
      return;
    }
    const defaultAgent = agents.data?.items.find((agent) => agent.is_default && agent.status === "active");
    if (defaultAgent && !form.getValues("ai_agent_id")) form.setValue("ai_agent_id", defaultAgent.id);
  }, [agents.data, form]);
  const run = useMutation({
    mutationFn: ({ request }: { request: AIPlaygroundRequest; retry: boolean }) => createPlaygroundExecution(request),
    onSuccess: (execution, { request, retry }) => {
      setExecutionId(execution.id);
      setPendingQuestion(request.question);
      if (!retry) setConversation((current) => [...current, { role: "user", content: request.question }]);
      setCopied(false);
    },
  });
  const retrievalPreview = useMutation({ mutationFn: previewPlaygroundRetrieval });
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
  useEffect(() => {
    const completed = execution.data;
    if (completed?.status !== "succeeded" || !completed.draft || appendedExecutionId.current === completed.id) return;
    appendedExecutionId.current = completed.id;
    setConversation((current) => [...current, { role: "assistant", content: completed.draft ?? "" }]);
    setPendingQuestion(undefined);
  }, [execution.data]);
  const canRun = ["owner", "admin", "agent"].includes(user.data?.role ?? "");
  const canManageBots = ["owner", "admin"].includes(user.data?.role ?? "");
  const busy = run.isPending || execution.data?.status === "queued" || execution.data?.status === "running";
  const selectedAgentId = form.watch("ai_agent_id");
  const selectedAgent = agents.data?.items.find((agent) => agent.id === selectedAgentId)
    ?? agents.data?.items.find((agent) => agent.is_default && agent.status === "active");
  const selectedBases = bases.data?.items.filter((base) => base.status === "active" && (selectedAgent?.knowledge_base_ids ?? []).includes(base.id)) ?? [];
  const selectedReadyDocuments = selectedBases.reduce((total, base) => total + base.ready_document_count, 0);
  const currentQuestion = form.watch("question");
  const previousAgentId = useRef<string | undefined>(selectedAgentId);
  useEffect(() => {
    if (previousAgentId.current === selectedAgentId) return;
    previousAgentId.current = selectedAgentId;
    lastRequest.current = undefined;
    setConversation([]);
    setExecutionId(undefined);
    setPendingQuestion(undefined);
    appendedExecutionId.current = undefined;
    run.reset();
  }, [selectedAgentId, run]);

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
      <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Chat with a selected bot across follow-up questions using its currently assigned knowledge sources. This private test conversation is not sent to customers.</p>
    </header>

    {!canRun && user.data && <p role="status" className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">Your role has read-only access to AI executions.</p>}
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
      <Panel>
        <PanelHeader title="Test conversation" description="Try follow-ups to see how this bot uses its assigned sources." action={<BookOpen size={17} className="text-slate-400"/>}/>
        <PanelBody>
          <form className="space-y-4" onSubmit={form.handleSubmit((values) => {
            const request: AIPlaygroundRequest = {
              question: values.question,
              conversation_history: conversation.slice(-6),
              ...(values.ai_agent_id ? { ai_agent_id: values.ai_agent_id } : {}),
            };
            lastRequest.current = request;
            setExecutionId(undefined);
            run.mutate({ request, retry: false }, { onSuccess: () => form.setValue("question", "") });
          })}>
            <div><label htmlFor="ai-playground-agent" className="mb-1.5 block text-sm font-medium text-slate-700">AI bot</label><Select id="ai-playground-agent" aria-label="AI bot" className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm" disabled={agents.isPending || agents.isError || !canRun || busy} {...form.register("ai_agent_id", { onChange: () => retrievalPreview.reset() })}><option value="">Default workspace bot</option>{agents.data?.items.filter((agent) => agent.status === "active").map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</Select>{agents.isError && <p role="alert" className="mt-1 text-xs text-amber-800">Bot list unavailable; the default bot will be used.</p>}{selectedAgent && <div className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5">{bases.isPending ? <p role="status" className="text-slate-500">Checking assigned knowledge sources…</p> : bases.isError ? <p role="alert" className="text-amber-800">Source readiness could not be loaded; the answer may not have supporting knowledge.</p> : selectedBases.length > 0 ? <><p className={selectedReadyDocuments > 0 ? "font-medium text-emerald-800" : "font-medium text-amber-800"}>{selectedReadyDocuments} ready documents across {selectedBases.length} assigned active {selectedBases.length === 1 ? "base" : "bases"}</p><p className="mt-0.5 text-slate-600">{selectedBases.map((base) => `${base.name} (${base.ready_document_count} ready)`).join(" · ")}</p>{selectedReadyDocuments === 0 && <p className="mt-1 text-amber-800">Process a document in the <Link className="font-semibold underline" href="/dashboard/knowledge">Knowledge Library</Link> before testing grounded answers.</p>}</> : <div className="text-amber-800"><p>This bot has no assigned active knowledge bases, so it cannot ground answers in documents.</p>{canManageBots ? <Link className="mt-1 inline-block font-semibold underline" href="/dashboard/ai/agents">Assign a knowledge base to this bot</Link> : <p className="mt-1">Ask a workspace Owner or Admin to assign a knowledge base.</p>}</div>}</div>}</div>
            <div>
              <label htmlFor="ai-playground-question" className="mb-1.5 block text-sm font-medium text-slate-700">Conversation</label>
              <div className="mb-3 max-h-80 space-y-3 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3" aria-live="polite" aria-label="Bot test conversation">
                {conversation.length === 0 && <p className="py-6 text-center text-sm text-slate-500">Ask a question, then follow up naturally.</p>}
                {conversation.map((message, index) => <div key={`${index}-${message.role}`} className={`max-w-[88%] whitespace-pre-wrap rounded-2xl px-3 py-2.5 text-sm leading-5 ${message.role === "user" ? "ml-auto bg-blue-700 text-white" : "border border-slate-200 bg-white text-slate-800"}`}><p className="mb-1 text-[11px] font-semibold opacity-70">{message.role === "user" ? "You" : selectedAgent?.name ?? "AI bot"}</p>{message.content}</div>)}
                {pendingQuestion && busy && <p role="status" className="flex items-center gap-2 text-xs text-slate-500"><LoaderCircle size={14} className="animate-spin"/>The bot is responding…</p>}
              </div>
              <Textarea id="ai-playground-question" placeholder="Ask a follow-up question…" className="min-h-24" disabled={!canRun || busy} aria-invalid={Boolean(form.formState.errors.question)} {...form.register("question", { onChange: () => retrievalPreview.reset() })}/>
              {form.formState.errors.question && <p role="alert" className="mt-1 text-sm text-red-700">{form.formState.errors.question.message}</p>}
            </div>
            <Button type="button" size="sm" variant="secondary" disabled={conversation.length === 0 || busy} onClick={() => { setConversation([]); setExecutionId(undefined); setPendingQuestion(undefined); lastRequest.current = undefined; appendedExecutionId.current = undefined; run.reset(); retrievalPreview.reset(); form.reset({ question: "", ai_agent_id: selectedAgentId || undefined }); }}><RotateCcw size={14}/>New chat</Button>
            <Button type="button" size="sm" variant="secondary" disabled={!canRun || busy || currentQuestion.trim().length < 4 || retrievalPreview.isPending} onClick={() => retrievalPreview.mutate({ question: currentQuestion.trim(), conversation_history: conversation.slice(-6), ...(selectedAgentId ? { ai_agent_id: selectedAgentId } : {}) })}>
              {retrievalPreview.isPending ? <><LoaderCircle size={15} className="animate-spin"/>Checking sources…</> : <><BookOpen size={15}/>Check source matches</>}
            </Button>
            <Button type="submit" disabled={!canRun || busy}>
              {busy ? <><LoaderCircle size={16} className="animate-spin"/>Thinking…</> : <><Send size={16}/>{conversation.length === 0 ? "Send message" : "Send follow-up"}</>}
            </Button>
          </form>
          {run.isError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{run.error.message}</p>}
          {retrievalPreview.isError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">Source matching could not be checked. The AI provider was not called; refresh the page and try again.</p>}
          {execution.isError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">The execution status could not be refreshed. Try reloading this page.</p>}
        </PanelBody>
      </Panel>

      <Panel aria-live="polite">
        <PanelHeader title="Latest response sources" description={execution.data?.safe_summary ?? "The active bot and its assigned sources are shown here."}/>
        <PanelBody>
          {retrievalPreview.data && <section className="mb-5 rounded-xl border border-blue-200 bg-blue-50/60 p-4" aria-live="polite" aria-label="Retrieval preview">
            <h2 className="text-sm font-semibold text-slate-900">Source match preview · {retrievalPreview.data.ai_agent_name}</h2>
            <p className="mt-1 text-xs leading-5 text-slate-700">{retrievalPreview.data.status === "matched"
              ? `Found ${retrievalPreview.data.matched_passage_count} matching passage${retrievalPreview.data.matched_passage_count === 1 ? "" : "s"} among ${retrievalPreview.data.ready_document_count} ready document${retrievalPreview.data.ready_document_count === 1 ? "" : "s"}. This is the same tenant- and bot-scoped search used by AI runs; no model call was made.`
              : retrievalPreview.data.status === "no_assigned_bases"
                ? "This bot has no active knowledge bases assigned. Assign a base in AI Bots before testing a grounded answer."
                : retrievalPreview.data.status === "no_ready_documents"
                  ? "The bot has assigned active bases, but none contain ready documents. Finish document processing or assign another base."
                  : retrievalPreview.data.status === "query_too_broad"
                    ? "The query did not contain searchable terms. Add a specific policy, product, or support topic and check again."
                    : "No passages matched this question in the bot’s assigned active sources. Try wording it with the policy or topic terms used in your documents."}</p>
            {retrievalPreview.data.retrieval_terms.length > 0 && <div className="mt-3"><p className="text-[11px] font-semibold text-slate-600">Normalized search terms</p><ul className="mt-1 flex flex-wrap gap-1.5" aria-label="Normalized search terms">{retrievalPreview.data.retrieval_terms.map((term, index) => <li key={`${index}-${term}`} className="max-w-full truncate rounded-md bg-white px-2 py-1 font-mono text-[11px] text-slate-700">{term}</li>)}</ul></div>}
            {retrievalPreview.data.sources.length > 0 && <ul className="mt-3 space-y-2">{retrievalPreview.data.sources.map((source) => <li key={`${source.document_id}-${source.chunk_index}`} className="rounded-lg border border-blue-100 bg-white p-3"><div className="flex flex-wrap items-start justify-between gap-2"><Link href={`/dashboard/knowledge/${encodeURIComponent(source.document_id)}`} className="text-xs font-semibold text-blue-700 hover:underline">{source.knowledge_base_name ? `${source.knowledge_base_name} · ` : ""}{source.document_name} · section {source.chunk_index + 1}</Link>{source.match_basis && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">{source.match_basis === "chunk_content" ? "Matched passage text" : "Matched source title"}</span>}</div><p className="mt-1 text-sm leading-5 text-slate-600">{source.excerpt}</p></li>)}</ul>}
          </section>}
          {!executionId && <p className="text-sm text-slate-500">{retrievalPreview.data ? "Run the AI after reviewing this preview to see its final answer grounding details." : "Send a message or check source matches to inspect this bot’s grounding."}</p>}
          {executionId && execution.isPending && <div className="space-y-3"><div className="h-4 w-2/3 animate-pulse rounded bg-slate-100"/><div className="h-24 animate-pulse rounded-xl bg-slate-100"/></div>}
          {execution.data && ["queued", "running"].includes(execution.data.status) && <p role="status" className="flex items-center gap-2 text-sm text-slate-600"><LoaderCircle size={16} className="animate-spin"/>The assistant is checking relevant documents…</p>}
          {execution.data?.status === "failed" && <div role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800"><p>{failureMessage(execution.data.error_code)}</p>{execution.data.correlation_id && <p className="mt-1 text-xs">Support reference: <SupportTraceLink correlationId={execution.data.correlation_id} /></p>}<Button type="button" size="sm" variant="secondary" className="mt-3" disabled={run.isPending || !lastRequest.current} onClick={() => { const request = lastRequest.current; if (!request) return; setExecutionId(undefined); run.reset(); run.mutate({ request, retry: true }); }}><RotateCcw size={14}/>{run.isPending ? "Retrying…" : "Retry this question"}</Button></div>}
          {execution.data?.status === "succeeded" && <>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500"><span>Draft only · bot configuration v{execution.data.ai_agent_config_version} · {execution.data.usage.total_tokens ?? 0} tokens</span><Button size="sm" variant="secondary" onClick={copyDraft}><Clipboard size={14}/>{copied ? "Copied" : "Copy latest answer"}</Button></div>
            {execution.data.citations.length > 0 ? <section className="mt-5" aria-label="Sources"><h2 className="text-sm font-semibold text-slate-800">Sources</h2><ul className="mt-2 space-y-2">{execution.data.citations.map((citation) => <li key={`${citation.document_id}-${citation.chunk_index}`} className="rounded-xl border border-slate-200 p-3"><div className="flex flex-wrap items-start justify-between gap-2"><Link href={`/dashboard/knowledge/${encodeURIComponent(citation.document_id)}`} className="text-xs font-semibold text-blue-700 hover:underline">{citation.knowledge_base_name ? `${citation.knowledge_base_name} · ` : ""}{citation.document_name} · section {citation.chunk_index + 1}</Link>{citation.match_basis && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">{citation.match_basis === "chunk_content" ? "Matched passage text" : "Matched source title"}</span>}</div><p className="mt-1 text-sm leading-5 text-slate-600">{citation.excerpt}</p></li>)}</ul></section> : <p className="mt-4 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">No matching knowledge sources were found. Verify the answer before using it.</p>}
          </>}
        </PanelBody>
      </Panel>
    </div>
  </div>;
}
