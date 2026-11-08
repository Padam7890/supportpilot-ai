"use client";

import { Checkbox } from "@/components/ui";
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CircleDollarSign, Clock3, LoaderCircle, Plus, Save, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { formatDateTime } from "@/lib/utils";
import { activateAIAgent, createAIAgent, aiAgentAuditKey, aiAgentsKey, deactivateAIAgent, getAIAgentAudit, listAIAgents, makeAIAgentDefault, updateAIAgent, type AIAgent, type AIAgentTool } from "../api/ai-agent-api";
import { knowledgeBaseKey, listKnowledgeBases, type KnowledgeBase } from "@/features/knowledge/api/knowledge-base-api";
import { analyticsQueryKeys, getAIUsage } from "@/features/analytics/api/analytics-api";

const DEFAULT_ALLOWED_TOOLS: AIAgentTool[] = ["recommend_products", "compare_products"];

export function AIAgentWorkspace() {
  const client = useQueryClient();
  const user = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const agents = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents });
  const bases = useQuery({ queryKey: knowledgeBaseKey, queryFn: listKnowledgeBases });
  const [selectedId, setSelectedId] = useState<string>();
  const [name, setName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [assignedIds, setAssignedIds] = useState<string[]>([]);
  const [allowedTools, setAllowedTools] = useState<AIAgentTool[]>(DEFAULT_ALLOWED_TOOLS);
  const [creating, setCreating] = useState(false);
  const selected = agents.data?.items.find((agent) => agent.id === selectedId);
  const archivedAssignedBases = bases.data?.items.filter((base) => base.status === "archived" && assignedIds.includes(base.id)) ?? [];
  const selectedKnowledgeBaseIds = selected?.knowledge_base_ids ?? [];
  const removedAssignmentIds = selectedKnowledgeBaseIds.filter((id) => !assignedIds.includes(id));
  const removedAssignmentNames = bases.data?.items.filter((base) => removedAssignmentIds.includes(base.id)).map((base) => base.name) ?? [];
  const canManage = ["owner", "admin"].includes(user.data?.role ?? "");
  const usageEnd = new Date().toISOString().slice(0, 10);
  const usageStartDate = new Date(Date.now() - 29 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const usage = useQuery({
    queryKey: analyticsQueryKeys.usage(usageStartDate, usageEnd),
    queryFn: () => getAIUsage(usageStartDate, usageEnd),
    enabled: Boolean(selectedId && canManage),
  });
  const selectedUsage = usage.data?.bots?.find((bot) => bot.bot_id === selectedId);
  const selectedConfigurationSaved = selected &&
    name.trim() === selected.name &&
    instructions === selected.system_instructions &&
    assignedIds.length === selectedKnowledgeBaseIds.length &&
    assignedIds.every((id) => selectedKnowledgeBaseIds.includes(id)) &&
    allowedTools.length === (selected.allowed_tools ?? DEFAULT_ALLOWED_TOOLS).length &&
    allowedTools.every((tool) => (selected.allowed_tools ?? DEFAULT_ALLOWED_TOOLS).includes(tool));
  const audit = useQuery({
    queryKey: aiAgentAuditKey(selected?.id),
    queryFn: () => getAIAgentAudit(selected!.id),
    enabled: Boolean(selected?.id && canManage),
  });

  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: aiAgentsKey }),
      client.invalidateQueries({ queryKey: knowledgeBaseKey }),
      client.invalidateQueries({ queryKey: aiAgentAuditKey(selectedId) }),
    ]);
  };
  const save = useMutation({
    mutationFn: async () => {
      if (creating) {
        return createAIAgent({ name, system_instructions: instructions, knowledge_base_ids: assignedIds, allowed_tools: allowedTools });
      }
      if (!selectedId) throw new Error("Choose a bot to edit");
      return updateAIAgent(selectedId, { name, system_instructions: instructions, knowledge_base_ids: assignedIds, allowed_tools: allowedTools });
    },
    onSuccess: async (agent) => { setCreating(false); setSelectedId(agent.id); setName(agent.name); setInstructions(agent.system_instructions); setAssignedIds(agent.knowledge_base_ids ?? []); setAllowedTools(agent.allowed_tools ?? DEFAULT_ALLOWED_TOOLS); await refresh(); },
  });
  const deactivate = useMutation({ mutationFn: deactivateAIAgent, onSuccess: refresh });
  const activate = useMutation({ mutationFn: activateAIAgent, onSuccess: refresh });
  const makeDefault = useMutation({
    mutationFn: makeAIAgentDefault,
    onSuccess: async (agent) => {
      setSelectedId(agent.id);
      await refresh();
    },
  });

  function startCreate() {
    setSelectedId(undefined);
    setCreating(true);
    setName("");
    setInstructions("");
    const activeDefaultBase = bases.data?.items.find((base) => base.is_default && base.status === "active");
    setAssignedIds(activeDefaultBase ? [activeDefaultBase.id] : []);
    setAllowedTools(DEFAULT_ALLOWED_TOOLS);
    save.reset();
    makeDefault.reset();
  }

  return <div className="space-y-6">
    <header><p className="flex items-center gap-2 text-sm font-semibold text-blue-700"><Sparkles size={16}/> Automation</p><h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-950">AI Bots</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Configure the assistant behavior and choose which knowledge bases each bot can use.</p></header>
    {!canManage && user.data && <p role="status" className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">Your role has read-only access to AI bot settings.</p>}
    <div className="grid items-start gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
      <Panel><PanelHeader title="Workspace bots" action={canManage ? <Button size="sm" disabled={bases.isPending} onClick={startCreate}><Plus size={15}/>New bot</Button> : undefined}/><PanelBody className="space-y-2">
        {agents.isPending && <p role="status" className="text-sm text-slate-500">Loading bots…</p>}
        {agents.isError && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800"><p>AI bots could not be loaded.</p><Button variant="unstyled" type="button" className="mt-1 font-semibold underline" onClick={() => agents.refetch()}>Retry</Button></div>}
        {agents.data?.items.map((agent) => <Button variant="unstyled" key={agent.id} type="button" onClick={() => { setCreating(false); setSelectedId(agent.id); setName(agent.name); setInstructions(agent.system_instructions); setAssignedIds(agent.knowledge_base_ids ?? []); setAllowedTools(agent.allowed_tools ?? DEFAULT_ALLOWED_TOOLS); save.reset(); makeDefault.reset(); }} className={`w-full rounded-xl border p-3 text-left transition ${selectedId === agent.id && !creating ? "border-blue-300 bg-blue-50" : "border-slate-200 hover:bg-slate-50"}`}><span className="flex items-center gap-2 text-sm font-semibold text-slate-800"><Bot size={16} className="text-blue-700"/>{agent.name}</span><span className="mt-1 block text-xs text-slate-600">{agent.is_default ? "Default bot" : "Custom bot"} · {agent.status}</span><span className="mt-1 block text-xs text-slate-500">{agentKnowledgeSummary(agent, bases.data?.items, bases.isPending, bases.isError)}</span></Button>)}
      </PanelBody></Panel>
      <Panel><PanelHeader title={creating ? "Create an AI bot" : selected ? "Bot configuration" : "Select a bot"} description="Instructions are sent to the configured model with retrieved, assigned knowledge only."/>
        <PanelBody className="space-y-5">
          {creating || selected ? <>
            <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Bot name</span><Input value={name} maxLength={120} disabled={!canManage} onChange={(event) => setName(event.target.value)} placeholder="Returns assistant"/></label>
            <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>System instructions</span><Textarea value={instructions} maxLength={8000} disabled={!canManage} onChange={(event) => setInstructions(event.target.value)} placeholder="Describe tone and response guidelines…" className="min-h-32"/><span className="text-xs font-normal text-slate-500">Keep policy facts in knowledge documents so answers can cite their source.</span></label>
            <fieldset disabled={!canManage} className="space-y-2"><legend className="text-sm font-semibold text-slate-800">Enabled shopping tools</legend><p className="mb-3 text-xs leading-5 text-slate-500">These tools only read the merchant catalog. Private order lookup and order changes continue through their separate verification and approval workflows.</p>{([{ id: "recommend_products", label: "Product recommendations", description: "Find and rank eligible products from this workspace catalog." }, { id: "compare_products", label: "Product comparisons", description: "Compare products already shown in this conversation." }] as const).map((tool) => <label key={tool.id} className="flex items-start gap-3 rounded-xl border border-slate-200 p-3 text-sm text-slate-700"><Checkbox className="mt-1" checked={allowedTools.includes(tool.id)} onCheckedChange={(checked) => setAllowedTools((current) => checked === true ? [...current, tool.id] : current.filter((item) => item !== tool.id))}/><span><span className="block font-medium">{tool.label}</span><span className="mt-0.5 block text-xs text-slate-500">{tool.description}</span></span></label>)}</fieldset>
            <fieldset disabled={!canManage || !bases.isSuccess} className="space-y-2"><legend className="mb-2 text-sm font-semibold text-slate-800">Assigned knowledge bases</legend>{creating && bases.isSuccess && bases.data.items.some((base) => base.is_default && base.status === "active") && <p className="mb-2 text-xs leading-5 text-slate-500">New bots start with the workspace default source assigned. You can change this selection or leave it empty.</p>}{bases.isPending && <p role="status" className="text-sm text-slate-500">Loading knowledge bases…</p>}{bases.isError && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800"><p>Knowledge bases could not be loaded, so assignments are locked until the list is available.</p><Button variant="unstyled" type="button" className="mt-1 font-semibold underline" onClick={() => bases.refetch()}>Retry</Button></div>}{bases.data?.items.filter((base) => base.status === "active").map((base) => <label key={base.id} className="flex items-start gap-3 rounded-xl border border-slate-200 p-3 text-sm text-slate-700"><Checkbox className="mt-1" checked={assignedIds.includes(base.id)} onCheckedChange={(checked) => setAssignedIds((current) => checked === true ? [...current, base.id] : current.filter((id) => id !== base.id))}/><span className="min-w-0 flex-1"><span className="block font-medium">{base.name}</span><span className={`mt-0.5 block text-xs ${base.ready_document_count > 0 ? "text-emerald-700" : "text-amber-700"}`}>{base.ready_document_count} ready of {base.document_count} {base.document_count === 1 ? "document" : "documents"}{base.processing_document_count > 0 ? ` · ${base.processing_document_count} processing` : ""}{base.failed_document_count > 0 ? ` · ${base.failed_document_count} failed` : ""}</span>{base.ready_document_count === 0 && <span className="mt-1 block text-xs text-slate-500">This base has no ready sources for answers yet.</span>}</span>{base.is_default && <span className="shrink-0 text-xs text-slate-500">Default</span>}</label>)}{bases.isSuccess && bases.data.items.filter((base) => base.status === "active").length === 0 && <p className="rounded-xl border border-dashed border-slate-300 p-3 text-sm text-slate-600">No active knowledge bases yet. This bot can be saved without sources, but it will only answer questions that do not require tenant knowledge.</p>}{archivedAssignedBases.length > 0 && <section className="mt-3 space-y-2 border-t border-slate-200 pt-3" aria-label="Archived assigned knowledge bases"><p className="text-xs leading-5 text-amber-800">Archived assignments are preserved but excluded from retrieval. Keep them assigned to restore access if the base is reactivated, or uncheck to remove the assignment.</p>{archivedAssignedBases.map((base) => <label key={base.id} className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50/60 p-3 text-sm text-slate-700"><Checkbox className="mt-1" checked onCheckedChange={() => setAssignedIds((current) => current.filter((id) => id !== base.id))}/><span className="min-w-0 flex-1"><span className="block font-medium">{base.name} · archived</span><span className="mt-0.5 block text-xs text-slate-600">{base.document_count} preserved {base.document_count === 1 ? "document" : "documents"}; unavailable to AI until restored.</span></span></label>)}</section>}</fieldset>
            {selected && canManage && removedAssignmentIds.length > 0 && <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><p className="font-semibold">Saving will remove {removedAssignmentIds.length} source assignment{removedAssignmentIds.length === 1 ? "" : "s"}.</p>{removedAssignmentNames.length > 0 && <p className="mt-1">{removedAssignmentNames.join(", ")}</p>}<p className="mt-1 leading-5">Queued executions use the bot’s current source assignments when retrieval runs, so they may no longer cite these bases.</p></div>}
            {selected && canManage && <section aria-labelledby="bot-performance-title" className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center gap-2"><CircleDollarSign size={16} className="text-violet-700"/><h2 id="bot-performance-title" className="text-sm font-semibold text-slate-900">Bot performance · last 30 days</h2></div>
              <p className="mt-1 text-xs text-slate-600">Counts and token estimates come from persisted AI executions. Cost is shown only when provider rates are configured.</p>
              {usage.isPending && <p role="status" className="mt-3 text-sm text-slate-500">Loading bot performance…</p>}
              {usage.isError && <p role="alert" className="mt-3 text-sm text-red-700">Bot performance could not be loaded.</p>}
              {usage.isSuccess && !selectedUsage && <p className="mt-3 text-sm text-slate-500">No executions for this bot in the selected period.</p>}
              {selectedUsage && <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <UsageMetric label="Executions" value={selectedUsage.executions.toLocaleString()}/>
                <UsageMetric label="Succeeded · failed" value={`${selectedUsage.succeeded} · ${selectedUsage.failed}`}/>
                <UsageMetric label="Tokens" value={(selectedUsage.prompt_tokens + selectedUsage.completion_tokens).toLocaleString()}/>
                <UsageMetric label="Average latency" value={selectedUsage.average_latency_ms == null ? "—" : `${selectedUsage.average_latency_ms.toLocaleString()} ms`}/>
                <div className="col-span-2 rounded-lg bg-white px-3 py-2 sm:col-span-4"><p className="text-[11px] font-medium text-slate-500">Estimated cost</p><p className="mt-0.5 text-sm font-semibold text-slate-900">{selectedUsage.estimated_cost_usd == null ? "Provider rates not configured" : `$${selectedUsage.estimated_cost_usd.toFixed(4)} USD`}</p></div>
              </div>}
            </section>}
            {save.isError && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{save.error.message || "Bot settings could not be saved."}</p>}
            {save.isSuccess && <p role="status" className="text-sm text-emerald-700">Bot settings saved.</p>}
            {makeDefault.isError && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">The workspace default bot could not be changed.</p>}
            {makeDefault.isSuccess && selected?.id === makeDefault.data.id && <p role="status" className="text-sm text-emerald-700">{makeDefault.data.name} is now the workspace default. Explicit widget bot selections are unchanged.</p>}
            <div className="flex flex-wrap items-center gap-2">{canManage && <Button disabled={save.isPending || !name.trim() || !bases.isSuccess} onClick={() => save.mutate()}>{save.isPending ? <LoaderCircle size={15} className="animate-spin"/> : <Save size={15}/>} {creating ? "Create bot" : "Save changes"}</Button>}{canManage && selected && selected.status === "active" && !creating && selectedConfigurationSaved && <Link className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500" href={`/dashboard/ai?ai_agent_id=${encodeURIComponent(selected.id)}`}><Sparkles size={15}/>Test bot</Link>}{canManage && selected && !selected.is_default && selected.status === "active" && <Button variant="secondary" disabled={deactivate.isPending || makeDefault.isPending} onClick={() => deactivate.mutate(selected.id)}>Deactivate bot</Button>}{canManage && selected && !selected.is_default && selected.status === "active" && <Button variant="secondary" disabled={makeDefault.isPending || deactivate.isPending} onClick={() => makeDefault.mutate(selected.id)}>{makeDefault.isPending ? "Setting default…" : "Make default"}</Button>}{canManage && selected && selected.status === "inactive" && <Button variant="secondary" disabled={activate.isPending} onClick={() => activate.mutate(selected.id)}>Activate bot</Button>}{selected?.is_default && <span className="self-center text-xs text-slate-500">This active bot is the default for workspace requests that do not select a bot.</span>}</div>
          </> : <p className="py-6 text-sm text-slate-500">Choose a bot from the list or create one. Existing workspaces use the default SupportPilot Assistant.</p>}
          {selected && canManage && <section aria-labelledby="bot-audit-title" className="border-t border-slate-200 pt-5">
            <div className="flex items-center gap-2"><Clock3 size={16} className="text-slate-500"/><h2 id="bot-audit-title" className="text-sm font-semibold text-slate-900">Configuration history</h2></div>
            <p className="mt-1 text-xs text-slate-600">Recent changes to this bot. Instruction text is never included in the audit history.</p>
            {audit.isPending && <p role="status" className="mt-3 text-sm text-slate-500">Loading history…</p>}
            {audit.isError && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">Configuration history could not be loaded.</p>}
            {audit.data?.items?.length === 0 && <p className="mt-3 text-sm text-slate-500">No configuration changes recorded yet.</p>}
            {audit.data?.items && audit.data.items.length > 0 && <ol className="mt-3 divide-y divide-slate-100 rounded-xl border border-slate-200">
              {audit.data.items.map((entry) => <li key={entry.id} className="flex flex-wrap items-start justify-between gap-2 p-3">
                <div><p className="text-sm font-medium text-slate-800">{auditEventLabel(entry.event_type)}</p><p className="mt-0.5 text-xs text-slate-600">{entry.actor_name} · version {entry.config_version}{changedFields(entry.details).length > 0 ? ` · ${changedFields(entry.details).join(", ")}` : ""}</p></div>
                <time className="shrink-0 text-xs text-slate-500" dateTime={entry.created_at}>{formatDateTime(entry.created_at)}</time>
              </li>)}
            </ol>}
          </section>}
        </PanelBody>
      </Panel>
    </div>
  </div>;
}

function agentKnowledgeSummary(
  agent: AIAgent,
  knowledgeBases: KnowledgeBase[] | undefined,
  isLoading: boolean,
  hasError: boolean,
): string {
  if (isLoading) return "Loading source assignments…";
  if (hasError || !knowledgeBases) return "Source summary unavailable";

  const assignedIds = new Set(agent.knowledge_base_ids ?? []);
  const activeBases = knowledgeBases.filter((base) => base.status === "active" && assignedIds.has(base.id));
  const readyDocuments = activeBases.reduce((total, base) => total + base.ready_document_count, 0);
  if (activeBases.length === 0) return "No active knowledge sources";

  const visibleNames = activeBases.slice(0, 2).map((base) => base.name);
  const baseNames = activeBases.length > visibleNames.length
    ? `${visibleNames.join(", ")} + ${activeBases.length - visibleNames.length} more`
    : visibleNames.join(", ");

  return `${baseNames} · ${readyDocuments} ready ${readyDocuments === 1 ? "document" : "documents"}`;
}

function auditEventLabel(eventType: string) {
  const labels: Record<string, string> = {
    created: "Bot created",
    updated: "Bot settings updated",
    knowledge_bases_changed: "Knowledge base assignments changed",
    activated: "Bot activated",
    deactivated: "Bot deactivated",
  };
  return labels[eventType] ?? "Bot configuration changed";
}

function changedFields(details: Record<string, unknown>) {
  const fields = details.changed_fields;
  return Array.isArray(fields)
    ? fields.filter((field): field is string => typeof field === "string").map((field) => field === "is_default" ? "workspace default" : field.replaceAll("_", " "))
    : [];
}

function UsageMetric({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded-lg bg-white px-3 py-2"><p className="text-[11px] font-medium text-slate-500">{label}</p><p className="mt-0.5 truncate text-sm font-semibold text-slate-900">{value}</p></div>;
}
