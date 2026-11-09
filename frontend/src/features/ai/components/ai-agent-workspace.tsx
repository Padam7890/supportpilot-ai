"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, LoaderCircle, Pencil, Plus, Save, Sparkles, Trash2, X } from "lucide-react";
import { Checkbox } from "@/components/ui";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { activateAIAgent, createAIAgent, aiAgentsKey, deactivateAIAgent, listAIAgents, makeAIAgentDefault, updateAIAgent, type AIAgent, type AIAgentTool } from "../api/ai-agent-api";
import { knowledgeBaseKey, listKnowledgeBases, type KnowledgeBase } from "@/features/knowledge/api/knowledge-base-api";

const DEFAULT_ALLOWED_TOOLS: AIAgentTool[] = ["recommend_products", "compare_products"];

export function AIAgentWorkspace() {
  const client = useQueryClient();
  const user = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const agents = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents });
  const bases = useQuery({ queryKey: knowledgeBaseKey, queryFn: listKnowledgeBases });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [deactivateTarget, setDeactivateTarget] = useState<AIAgent>();
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string>();
  const [name, setName] = useState<string>();
  const [instructions, setInstructions] = useState<string>();
  const [assignedIds, setAssignedIds] = useState<string[]>();
  const [allowedTools, setAllowedTools] = useState<AIAgentTool[]>();
  const selected = agents.data?.items.find((agent) => agent.id === selectedId);
  const defaultBaseId = bases.data?.items.find((base) => base.is_default && base.status === "active")?.id;
  const formName = name ?? selected?.name ?? "";
  const formInstructions = instructions ?? selected?.system_instructions ?? "";
  const formAssignedIds = assignedIds ?? (creating ? (defaultBaseId ? [defaultBaseId] : []) : selected?.knowledge_base_ids ?? []);
  const formAllowedTools = allowedTools ?? selected?.allowed_tools ?? DEFAULT_ALLOWED_TOOLS;
  const archivedAssignedBases = bases.data?.items.filter((base) => base.status === "archived" && formAssignedIds.includes(base.id)) ?? [];
  const selectedKnowledgeBaseIds = selected?.knowledge_base_ids ?? [];
  const removedAssignmentIds = selectedKnowledgeBaseIds.filter((id) => !formAssignedIds.includes(id));
  const removedAssignmentNames = bases.data?.items.filter((base) => removedAssignmentIds.includes(base.id)).map((base) => base.name) ?? [];
  const canManage = ["owner", "admin"].includes(user.data?.role ?? "");
  const selectedConfigurationSaved = selected && formName.trim() === selected.name && formInstructions === selected.system_instructions &&
    formAssignedIds.length === selectedKnowledgeBaseIds.length && formAssignedIds.every((id) => selectedKnowledgeBaseIds.includes(id)) &&
    formAllowedTools.length === (selected.allowed_tools ?? DEFAULT_ALLOWED_TOOLS).length && formAllowedTools.every((tool) => (selected.allowed_tools ?? DEFAULT_ALLOWED_TOOLS).includes(tool));
  const refresh = async () => Promise.all([
    client.invalidateQueries({ queryKey: aiAgentsKey }),
    client.invalidateQueries({ queryKey: knowledgeBaseKey }),
  ]);
  const save = useMutation({
    mutationFn: async () => creating
      ? createAIAgent({ name: formName, system_instructions: formInstructions, knowledge_base_ids: formAssignedIds, allowed_tools: formAllowedTools })
      : selectedId ? updateAIAgent(selectedId, { name: formName, system_instructions: formInstructions, knowledge_base_ids: formAssignedIds, allowed_tools: formAllowedTools }) : Promise.reject(new Error("Choose a bot to edit")),
    onSuccess: async (agent) => {
      setName(agent.name); setInstructions(agent.system_instructions); setAssignedIds(agent.knowledge_base_ids ?? []); setAllowedTools(agent.allowed_tools ?? DEFAULT_ALLOWED_TOOLS);
      await refresh();
      setCreating(false);
      setSelectedId(agent.id);
    },
  });
  const deactivate = useMutation({ mutationFn: deactivateAIAgent, onSuccess: refresh });
  const activate = useMutation({ mutationFn: activateAIAgent, onSuccess: refresh });
  const makeDefault = useMutation({ mutationFn: makeAIAgentDefault, onSuccess: refresh });

  const beginCreate = () => {
    setCreating(true); setSelectedId(undefined); setName(""); setInstructions(""); setAssignedIds(defaultBaseId ? [defaultBaseId] : []); setAllowedTools(DEFAULT_ALLOWED_TOOLS); save.reset(); setDrawerOpen(true);
  };
  const beginEdit = (id: string) => {
    const agent = agents.data?.items.find((item) => item.id === id);
    setCreating(false); setSelectedId(id); setName(agent?.name); setInstructions(agent?.system_instructions); setAssignedIds(agent?.knowledge_base_ids ?? []); setAllowedTools(agent?.allowed_tools ?? DEFAULT_ALLOWED_TOOLS); save.reset(); setDrawerOpen(true);
  };
  const closeDrawer = () => { setDrawerOpen(false); setCreating(false); setSelectedId(undefined); setName(undefined); setInstructions(undefined); setAssignedIds(undefined); setAllowedTools(undefined); save.reset(); };

  return <div className="space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="flex items-center gap-2 text-sm font-medium text-primary"><Sparkles size={16}/> AI Studio</p><h1 className="mt-1 text-2xl font-semibold tracking-tight">AI Bots</h1><p className="mt-1 text-sm text-muted-foreground">Manage bot instructions and the knowledge each assistant can use.</p></div>{canManage && <Button disabled={bases.isPending} onClick={beginCreate}><Plus/>New bot</Button>}</header>
    {!canManage && user.data && <p role="status" className="rounded-lg border p-3 text-sm text-muted-foreground">Your role has read-only access to AI bot settings.</p>}
    {agents.isPending && <p role="status" className="text-sm text-muted-foreground">Loading bots…</p>}
    {agents.isError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm">AI bots could not be loaded. <Button variant="link" className="ml-2" onClick={() => agents.refetch()}>Retry</Button></div>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{agents.data?.items.map((agent) => <article key={agent.id} className="group relative rounded-xl border bg-card transition-colors hover:bg-muted/40"><button type="button" onClick={() => beginEdit(agent.id)} className="w-full rounded-xl p-4 pr-24 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><span className="flex items-center gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><Bot size={18}/></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{agent.name}</span><span className="mt-0.5 block text-xs text-muted-foreground">{agent.is_default ? "Default bot" : "Custom bot"} · {agent.status}</span></span></span><span className="mt-4 block line-clamp-2 text-xs leading-5 text-muted-foreground">{agentKnowledgeSummary(agent, bases.data?.items, bases.isPending, bases.isError)}</span><span className="mt-4 block text-xs font-medium text-primary">Configure bot <span aria-hidden="true" className="ml-1 transition-transform group-hover:translate-x-0.5">→</span></span></button>{canManage && <div className="absolute right-3 top-3 flex items-center gap-1"><Button variant="ghost" size="icon-sm" aria-label={`Edit ${agent.name}`} title="Edit bot" onClick={() => beginEdit(agent.id)}><Pencil/></Button>{!agent.is_default && agent.status === "active" && <Button variant="ghost" size="icon-sm" aria-label={`Deactivate ${agent.name}`} title="Deactivate bot" className="text-muted-foreground hover:text-destructive" onClick={() => setDeactivateTarget(agent)}><Trash2/></Button>}</div>}</article>)}</div>
    {agents.data?.items.length === 0 && <div className="rounded-xl border border-dashed p-10 text-center"><Bot className="mx-auto size-8 text-muted-foreground"/><h2 className="mt-3 font-semibold">No bots yet</h2><p className="mt-1 text-sm text-muted-foreground">Create a bot to configure its knowledge and behavior.</p></div>}
    <ConfirmDialog open={Boolean(deactivateTarget)} onOpenChange={(open) => !open && setDeactivateTarget(undefined)} title="Deactivate this bot?" description={deactivateTarget ? `${deactivateTarget.name} will stop handling new conversations. Its configuration and history will be preserved.` : undefined} confirmLabel="Deactivate bot" pending={deactivate.isPending} pendingLabel="Deactivating…" onConfirm={() => { if (deactivateTarget) deactivate.mutate(deactivateTarget.id, { onSuccess: () => setDeactivateTarget(undefined) }); }}/>
    {deactivate.isError && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{deactivate.error.message || "This bot could not be deactivated. Remove it from the widget before trying again."}</p>}
    <Sheet open={drawerOpen} onOpenChange={(open) => open ? setDrawerOpen(true) : closeDrawer()}>
      <SheetContent showCloseButton={false} className="top-0 left-auto right-0 h-dvh w-[720px] max-w-[calc(100vw-1rem)] translate-x-0 translate-y-0 flex flex-col gap-0 overflow-hidden rounded-none border-l p-0 duration-300 data-open:animate-in data-open:slide-in-from-right data-closed:animate-out data-closed:slide-out-to-right sm:max-w-[calc(100vw-1rem)]">
        <SheetHeader className="flex-row items-start justify-between border-b px-6 py-4 text-left"><div><SheetTitle>{creating ? "Create an AI bot" : selected?.name ?? "Bot configuration"}</SheetTitle><SheetDescription className="mt-1">Configure the assistant, then test it before publishing changes.</SheetDescription></div><Button variant="ghost" size="icon-sm" aria-label="Close bot configuration" onClick={closeDrawer}><X/></Button></SheetHeader>
        {!creating && agents.isPending && <p role="status" className="p-6 text-sm text-muted-foreground">Loading bot configuration…</p>}
        {!creating && agents.isSuccess && !selected && <p role="alert" className="p-6 text-sm text-muted-foreground">This bot could not be found in the current workspace.</p>}
        {(creating || selected) && <main className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5 sm:p-6">
        <Panel><PanelHeader title="Configuration" description="Instructions are sent to the model together with retrieved knowledge from assigned bases."/><PanelBody className="space-y-5">
          <label className="block space-y-2 text-sm font-medium"><span>Bot name</span><Input value={formName} maxLength={120} disabled={!canManage} onChange={(event) => setName(event.target.value)} placeholder="Returns assistant"/></label>
          <label className="block space-y-2 text-sm font-medium"><span>System instructions</span><Textarea value={formInstructions} maxLength={8000} disabled={!canManage} onChange={(event) => setInstructions(event.target.value)} placeholder="Describe tone and response guidelines…" className="field-sizing-fixed h-64 min-h-64 max-h-64 resize-none overflow-y-auto"/><span className="text-xs font-normal text-muted-foreground">Keep policy facts in knowledge documents so answers can cite their source.</span></label>
          <fieldset disabled={!canManage} className="space-y-2"><legend className="text-sm font-semibold">Enabled shopping tools</legend><p className="mb-3 text-xs leading-5 text-muted-foreground">These tools only read the merchant catalog. Private order lookup and order changes use separate verification and approval workflows.</p>{([{ id: "recommend_products", label: "Product recommendations", description: "Find eligible products from this workspace catalog." }, { id: "compare_products", label: "Product comparisons", description: "Compare products already shown in the conversation." }] as const).map((tool) => <label key={tool.id} className="flex items-start gap-3 rounded-lg border p-3 text-sm"><Checkbox className="mt-1" checked={formAllowedTools.includes(tool.id)} onCheckedChange={(checked) => setAllowedTools(checked === true ? [...formAllowedTools, tool.id] : formAllowedTools.filter((item) => item !== tool.id))}/><span><span className="block font-medium">{tool.label}</span><span className="mt-0.5 block text-xs text-muted-foreground">{tool.description}</span></span></label>)}</fieldset>
          <fieldset disabled={!canManage || !bases.isSuccess} className="space-y-2"><legend className="mb-2 text-sm font-semibold">Assigned knowledge bases</legend>{creating && defaultBaseId && <p className="mb-2 text-xs text-muted-foreground">New bots start with the workspace default source assigned. You can change this selection or leave it empty.</p>}{bases.isPending && <p role="status" className="text-sm text-muted-foreground">Loading knowledge bases…</p>}{bases.isError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">Knowledge bases could not be loaded; assignments are locked. <Button variant="link" className="ml-2" onClick={() => bases.refetch()}>Retry</Button></div>}{bases.data?.items.filter((base) => base.status === "active").map((base) => <BaseAssignment key={base.id} base={base} checked={formAssignedIds.includes(base.id)} onChange={(checked) => setAssignedIds(checked ? [...formAssignedIds, base.id] : formAssignedIds.filter((id) => id !== base.id))}/>)}{bases.isSuccess && bases.data.items.filter((base) => base.status === "active").length === 0 && <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">No active knowledge bases yet. This bot will use the safe no-knowledge response for questions requiring tenant information.</p>}{archivedAssignedBases.length > 0 && <section className="mt-3 space-y-2 border-t pt-3"><p className="text-xs text-amber-700">Archived assignments are preserved but excluded from retrieval.</p>{archivedAssignedBases.map((base) => <BaseAssignment key={base.id} base={base} checked onChange={() => setAssignedIds(formAssignedIds.filter((id) => id !== base.id))} archived/>)}</section>}</fieldset>
          {selected && canManage && removedAssignmentIds.length > 0 && <div role="status" className="rounded-lg border border-amber-300/60 bg-amber-50/60 p-3 text-sm text-amber-900"><p className="font-medium">Saving will remove {removedAssignmentIds.length} source assignment{removedAssignmentIds.length === 1 ? "" : "s"}.</p>{removedAssignmentNames.length > 0 && <p className="mt-1">{removedAssignmentNames.join(", ")}</p>}<p className="mt-1 text-xs leading-5">Queued executions use the bot’s current source assignments when retrieval runs.</p></div>}
          {save.isError && <p role="alert" className="rounded-lg bg-destructive/5 p-3 text-sm text-destructive">{save.error.message || "Bot settings could not be saved."}</p>}{save.isSuccess && <p role="status" className="text-sm text-emerald-700">Bot settings saved.</p>}{makeDefault.isError && <p role="alert" className="text-sm text-destructive">The workspace default bot could not be changed.</p>}{makeDefault.isSuccess && selected?.id === makeDefault.data.id && <p role="status" className="text-sm text-emerald-700">{makeDefault.data.name} is now the workspace default.</p>}
          <div className="flex flex-wrap items-center gap-2 border-t pt-4">{canManage && <Button disabled={save.isPending || !formName.trim() || !bases.isSuccess} onClick={() => save.mutate()}>{save.isPending ? <LoaderCircle className="animate-spin"/> : <Save/>}{creating ? "Create bot" : "Save changes"}</Button>}{canManage && selected?.status === "active" && selectedConfigurationSaved && <Link className="inline-flex h-9 items-center gap-2 rounded-md border px-3.5 text-sm font-medium hover:bg-muted" href={`/dashboard/ai?ai_agent_id=${encodeURIComponent(selected.id)}`}><Sparkles size={16}/>Test bot</Link>}{canManage && selected && !selected.is_default && selected.status === "active" && <Button variant="secondary" disabled={deactivate.isPending || makeDefault.isPending} onClick={() => deactivate.mutate(selected.id)}>Deactivate bot</Button>}{canManage && selected && !selected.is_default && selected.status === "active" && <Button variant="outline" disabled={makeDefault.isPending || deactivate.isPending} onClick={() => makeDefault.mutate(selected.id)}>{makeDefault.isPending ? "Setting default…" : "Make default"}</Button>}{canManage && selected?.status === "inactive" && <Button variant="secondary" disabled={activate.isPending} onClick={() => activate.mutate(selected.id)}>Activate bot</Button>}{selected?.is_default && <span className="text-xs text-muted-foreground">Default for workspace requests without an explicit bot.</span>}</div>
        </PanelBody></Panel>
        {selected && canManage && <div className="border-t pt-4"><Link className="inline-flex h-9 items-center rounded-md px-3 text-sm font-medium text-primary hover:bg-muted" href={`/dashboard/ai/agents/${selected.id}/performance`}>Performance &amp; configuration history</Link></div>}
        </main>}
      </SheetContent>
    </Sheet>
  </div>;
}

function BaseAssignment({ base, checked, onChange, archived = false }: { base: KnowledgeBase; checked: boolean; onChange: (checked: boolean) => void; archived?: boolean }) {
  return <label className={`flex items-start gap-3 rounded-lg border p-3 text-sm ${archived ? "border-amber-300/60 bg-amber-50/50" : ""}`}><Checkbox className="mt-1" checked={checked} onCheckedChange={(value) => onChange(value === true)}/><span className="min-w-0 flex-1"><span className="block font-medium">{base.name}{archived ? " · archived" : ""}</span><span className="mt-0.5 block text-xs text-muted-foreground">{base.description || (archived ? "Archived source; excluded from retrieval." : "Available to this bot for grounded responses.")}</span></span>{base.is_default && <span className="shrink-0 text-xs text-muted-foreground">Default</span>}</label>;
}

function agentKnowledgeSummary(agent: AIAgent, knowledgeBases: KnowledgeBase[] | undefined, isLoading: boolean, hasError: boolean): string {
  if (isLoading) return "Loading source assignments…";
  if (hasError || !knowledgeBases) return "Source summary unavailable";
  const assigned = new Set(agent.knowledge_base_ids ?? []);
  const active = knowledgeBases.filter((base) => base.status === "active" && assigned.has(base.id));
  if (!active.length) return "No active knowledge sources";
  const names = active.slice(0, 2).map((base) => base.name).join(", ");
  return `${names}${active.length > 2 ? ` + ${active.length - 2} more` : ""}`;
}
