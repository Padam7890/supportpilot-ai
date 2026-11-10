"use client";

import { Checkbox } from "@/components/ui";
import { Input, Select, Textarea } from "@/components/ui";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Check, Copy, MessageCircle, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ApiError } from "@/lib/api/errors";
import { aiAgentsKey, listAIAgents } from "@/features/ai/api/ai-agent-api";
import { knowledgeBaseKey, listKnowledgeBases } from "@/features/knowledge/api/knowledge-base-api";
import { createWidgetConfig, getWidgetConfig, previewWidgetRouting, updateWidgetConfig, widgetConfigKey, type WidgetRoutingPreview } from "../api/widget-api";
import type { WidgetPreviewDraft } from "@/features/widget/types/widget-preview";

function isSafeStorefrontOrigin(value: string): boolean {
  try {
    const parsed = new URL(value);
    return (parsed.protocol === "https:" || parsed.protocol === "http:") && parsed.origin === value;
  } catch {
    return false;
  }
}

export function StorefrontWidgetCard({ onPreviewChange }: { onPreviewChange?: (draft: WidgetPreviewDraft) => void } = {}) {
  const client = useQueryClient();
  const config = useQuery({
    queryKey: widgetConfigKey,
    queryFn: getWidgetConfig,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });
  const agents = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents });
  const bases = useQuery({ queryKey: knowledgeBaseKey, queryFn: listKnowledgeBases });
  const [originsDraft, setOriginsDraft] = useState<string>();
  const [enabledDraft, setEnabledDraft] = useState<boolean>();
  const [aiEnabledDraft, setAiEnabledDraft] = useState<boolean>();
  const [aiModeDraft, setAiModeDraft] = useState<"draft_only" | "auto_reply">();
  const [assistantNameDraft, setAssistantNameDraft] = useState<string>();
  const [welcomeMessageDraft, setWelcomeMessageDraft] = useState<string>();
  const [agentDraft, setAgentDraft] = useState<string[]>();
  const [sampleRoutingMessage, setSampleRoutingMessage] = useState("");
  const [copied, setCopied] = useState(false);
  const appBase = (process.env.NEXT_PUBLIC_SUPPORTPILOT_APP_URL || (typeof window !== "undefined" ? window.location.origin : "")).replace(/\/$/, "");
  const widgetScriptVersion = "2026-11-10-widget-paragraphs-v6";
  const originsText = originsDraft ?? config.data?.allowed_origins.join("\n") ?? "";
  const enabled = enabledDraft ?? config.data?.enabled ?? true;
  const aiEnabled = aiEnabledDraft ?? config.data?.ai_enabled ?? false;
  const aiReplyMode = aiModeDraft ?? config.data?.ai_reply_mode ?? "draft_only";
  const assistantName = assistantNameDraft ?? config.data?.assistant_name ?? "SupportPilot AI";
  const welcomeMessage = welcomeMessageDraft ?? config.data?.welcome_message ?? "Hi! How can we help?";
  const storefrontOrigin = config.data?.allowed_origins.find(isSafeStorefrontOrigin);
  const defaultAgentId = agents.data?.items.find((agent) => agent.is_default && agent.status === "active")?.id;
  const configuredAgentIds = config.data?.ai_agent_ids ?? (config.data?.ai_agent_id ? [config.data.ai_agent_id] : defaultAgentId ? [defaultAgentId] : []);
  const activeAgentIds = new Set(agents.data?.items.filter((agent) => agent.status === "active").map((agent) => agent.id) ?? []);
  const activeConfiguredAgentIds = agents.isSuccess
    ? configuredAgentIds.filter((id) => activeAgentIds.has(id))
    : configuredAgentIds;
  const initialAgentSelection = agents.isSuccess && activeConfiguredAgentIds.length === 0 && defaultAgentId
    ? [defaultAgentId]
    : configuredAgentIds;
  const selectedAgents = (agentDraft ?? initialAgentSelection).filter((id) => !agents.isSuccess || activeAgentIds.has(id));
  const inactiveConfiguredAgentCount = agents.isSuccess
    ? configuredAgentIds.filter((id) => !activeAgentIds.has(id)).length
    : 0;
  const selectedAgentNames = agents.data?.items
    .filter((agent) => agent.status === "active" && selectedAgents.includes(agent.id))
    .map((agent) => agent.name) ?? [];
  const selectedAgentNamesKey = selectedAgentNames.join("\u001f");
  const origins = useMemo(() => originsText.split(/[\n,]/).map((value) => value.trim()).filter(Boolean), [originsText]);

  useEffect(() => {
    if (!onPreviewChange || agents.isPending || agents.isError) return;
    onPreviewChange({
      enabled,
      aiEnabled,
      replyMode: aiReplyMode,
      botNames: selectedAgentNamesKey ? selectedAgentNamesKey.split("\u001f") : [],
      assistantName,
      welcomeMessage,
    });
  }, [
    config.data,
    agents.isError,
    agents.isPending,
    enabled,
    aiEnabled,
    aiReplyMode,
    assistantName,
    welcomeMessage,
    selectedAgentNamesKey,
    onPreviewChange,
  ]);
  const save = useMutation({
    mutationFn: () => config.data
      ? updateWidgetConfig({ allowed_origins: origins, enabled, collect_contact: config.data.collect_contact, ai_enabled: aiEnabled, ai_reply_mode: aiReplyMode, assistant_name: assistantName, welcome_message: welcomeMessage, ai_agent_id: selectedAgents[0], ai_agent_ids: selectedAgents })
      : createWidgetConfig({ allowed_origins: origins, ai_enabled: aiEnabled, ai_reply_mode: aiReplyMode, assistant_name: assistantName, welcome_message: welcomeMessage, ai_agent_id: selectedAgents[0], ai_agent_ids: selectedAgents }),
    onSuccess: async (saved) => {
      client.setQueryData(widgetConfigKey, saved);
      setOriginsDraft(undefined);
      setEnabledDraft(undefined);
      setAiEnabledDraft(undefined);
      setAiModeDraft(undefined);
      setAssistantNameDraft(undefined);
      setWelcomeMessageDraft(undefined);
      setAgentDraft(undefined);
      await client.invalidateQueries({ queryKey: widgetConfigKey });
    },
  });
  const routingPreview = useMutation({ mutationFn: previewWidgetRouting });
  const embed = config.data && appBase
    ? `<script async src="${appBase}/supportpilot-widget.js?v=${widgetScriptVersion}" data-widget-id="${config.data.public_id}" data-api-base="${appBase}/api"></script>`
    : "";

  async function copySnippet() {
    if (!embed) return;
    await navigator.clipboard.writeText(embed);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return <Panel>
    <PanelHeader title="Shopify storefront chat" description="Create a ticket and conversation from the first visitor message." action={<span className="grid size-9 place-items-center rounded-xl bg-blue-50 text-blue-700"><MessageCircle size={18}/></span>}/>
    <PanelBody className="space-y-4">
      <p className="flex items-start gap-2 rounded-xl bg-blue-50 p-3 text-xs leading-5 text-blue-900"><ShieldCheck size={15} className="mt-0.5 shrink-0"/>The public widget ID only locates this widget. The backend checks the configured storefront origin, rate limits submissions, and issues a visitor token scoped to one conversation.</p>
      {config.isPending && <p role="status" className="text-sm text-slate-500">Loading widget settings…</p>}
      {config.isError && <div role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700"><p>{config.error instanceof ApiError ? config.error.message : "Widget settings could not be loaded."}</p>{config.error instanceof ApiError && <p className="mt-1 text-xs">API status {config.error.status}{config.error.code ? ` · ${config.error.code}` : ""}</p>}</div>}
      <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Allowed storefront origins</span><Textarea aria-label="Allowed storefront origins" value={originsText} onChange={(event) => setOriginsDraft(event.target.value)} placeholder="https://your-store.myshopify.com" rows={3} className="w-full rounded-xl border border-slate-200 bg-white p-3 text-sm outline-none focus:border-blue-500"/><span className="block text-xs font-normal text-slate-500">One exact origin per line, including https://. Add your Shopify storefront domain.</span></label>
      {config.data && <label className="flex items-center gap-2 text-sm text-slate-700"><Checkbox checked={enabled} onCheckedChange={(checked) => setEnabledDraft(checked === true)}/>Widget enabled</label>}
      {config.data && <section aria-label="Widget channel activity" className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3">
        <span className={`mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg ${!config.data.enabled ? "bg-slate-100 text-slate-500" : config.data.last_widget_load_at ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}><Activity size={16}/></span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900">{!config.data.enabled ? "Widget disabled" : config.data.last_widget_load_at ? "Widget confirmed on storefront" : "Waiting for widget to open on storefront"}</p>
          <p className="mt-0.5 text-xs leading-5 text-slate-600">{!config.data.enabled ? "Customers cannot start new widget conversations while this channel is disabled." : config.data.last_widget_load_at ? `Last confirmed load: ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(config.data.last_widget_load_at))}.${config.data.last_customer_message_at ? ` Latest customer message: ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(config.data.last_customer_message_at))}.` : " No customer messages have been received yet."}` : "Open the storefront and launch the chat widget from an allowed origin. SupportPilot will confirm the widget after it successfully loads its configuration."}</p>
          {config.data.enabled && storefrontOrigin && <a href={storefrontOrigin} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex min-h-9 items-center rounded-lg border border-slate-200 px-3 text-xs font-semibold text-blue-700 hover:bg-blue-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Open storefront to verify</a>}
        </div>
      </section>}
      <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4" aria-labelledby="widget-branding-title">
        <div><h3 id="widget-branding-title" className="text-sm font-semibold text-slate-900">Widget greeting</h3><p className="mt-1 text-xs leading-5 text-slate-600">Customize the assistant name and the first message shoppers see.</p></div>
        <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Assistant name</span><Input aria-label="Assistant name" value={assistantName} maxLength={60} onChange={(event) => setAssistantNameDraft(event.target.value)} placeholder="Support assistant" className="min-h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm"/></label>
        <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Welcome message</span><Textarea aria-label="Welcome message" value={welcomeMessage} maxLength={240} rows={2} onChange={(event) => setWelcomeMessageDraft(event.target.value)} placeholder="Hi! How can we help?" className="w-full rounded-lg border border-slate-200 bg-white p-3 text-sm"/><span className="text-xs font-normal text-slate-500">{welcomeMessage.length}/240 characters</span></label>
      </section>
      <section className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4" aria-labelledby="widget-ai-title">
        <div><h3 id="widget-ai-title" className="text-sm font-semibold text-slate-900">AI replies</h3><p className="mt-1 text-xs leading-5 text-slate-600">Choose multiple bots. New messages are routed to the selected bot whose assigned knowledge best matches the question. Sensitive requests still go to a teammate.</p></div>
        {inactiveConfiguredAgentCount > 0 && <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">{inactiveConfiguredAgentCount} configured {inactiveConfiguredAgentCount === 1 ? "bot is" : "bots are"} inactive and cannot handle new widget messages. They are omitted from this active selection{activeConfiguredAgentIds.length === 0 && defaultAgentId ? "; the active default bot is selected as a replacement" : ""}. Saving updates widget routing.</p>}
        <fieldset disabled={agents.isPending || agents.isError || agents.data?.items.length === 0} className="space-y-2"><legend className="mb-1 text-sm font-medium text-slate-700">Bots available to the widget</legend><p className="text-xs leading-5 text-slate-500">The best assigned-source match handles each message. If none matches, the primary bot below is the fallback.</p>{agents.data?.items.filter((agent) => agent.status === "active").map((agent) => { const assignedBases = bases.data?.items.filter((base) => base.status === "active" && (agent.knowledge_base_ids ?? []).includes(base.id)) ?? []; const readyCount = assignedBases.reduce((total, base) => total + base.ready_document_count, 0); const tools = agent.allowed_tools ?? ["recommend_products", "compare_products"]; const shoppingCapabilities = [tools.includes("recommend_products") ? "recommendations" : null, tools.includes("compare_products") ? "comparisons" : null].filter(Boolean); const isSelected = selectedAgents.includes(agent.id); const isPrimary = selectedAgents[0] === agent.id; return <div key={agent.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"><div className="flex items-start gap-2"><Checkbox className="mt-1" aria-label={`Use ${agent.name} in widget`} checked={isSelected} onCheckedChange={(checked) => { routingPreview.reset(); setAgentDraft((current) => { const currentIds = current ?? selectedAgents; return checked === true ? [...new Set([...currentIds, agent.id])] : currentIds.filter((id) => id !== agent.id); }); }}/><div className="min-w-0 flex-1"><p>{agent.name}{agent.is_default ? " · default" : ""}</p><span className={`mt-0.5 block text-xs ${shoppingCapabilities.length ? "text-slate-600" : "text-amber-800"}`}>{shoppingCapabilities.length ? `Shopping tools: ${shoppingCapabilities.join(" and ")}` : "Product tools are disabled for this bot."}</span>{bases.isPending && <span className="mt-0.5 block text-xs text-slate-500">Checking assigned knowledge sources…</span>}{bases.isError && <span className="mt-0.5 block text-xs text-amber-800">Knowledge source readiness is unavailable.</span>}{bases.isSuccess && (assignedBases.length > 0 ? <span className={`mt-0.5 block text-xs ${readyCount > 0 ? "text-emerald-700" : "text-amber-800"}`}>{readyCount} ready source {readyCount === 1 ? "document" : "documents"} across {assignedBases.length} assigned {assignedBases.length === 1 ? "base" : "bases"}</span> : <span className="mt-0.5 block text-xs text-amber-800">No active knowledge bases assigned; this bot may hand off store-specific questions.</span>)}</div><label className={`flex shrink-0 items-center gap-1.5 text-xs ${isSelected ? "text-slate-700" : "text-slate-400"}`}><input type="radio" name="widget-primary-ai-bot" aria-label={`Set ${agent.name} as primary fallback bot`} checked={isPrimary} disabled={!isSelected} onChange={() => { routingPreview.reset(); setAgentDraft((current) => { const currentIds = current ?? selectedAgents; return [agent.id, ...currentIds.filter((id) => id !== agent.id)]; }); }}/><span>{isPrimary ? "Primary fallback" : "Make primary"}</span></label></div></div>; })}{agents.isError && <span role="alert" className="block text-xs text-red-700">AI bots could not be loaded.</span>}{agents.data && agents.data.items.filter((agent) => agent.status === "active").length === 0 && <span className="block text-xs text-amber-800">Create or activate an AI bot before enabling widget replies.</span>}{selectedAgents.length === 0 && <span className="block text-xs text-amber-800">Select at least one bot.</span>}</fieldset>
        {config.data && <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3" aria-label="Test widget bot routing">
          <div><p className="text-sm font-medium text-slate-800">Preview bot routing</p><p className="mt-0.5 text-xs leading-5 text-slate-500">Try a sample message against the currently selected bots. This does not save settings or create a conversation.</p></div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input aria-label="Sample customer message" value={sampleRoutingMessage} onChange={(event) => { routingPreview.reset(); setSampleRoutingMessage(event.target.value); }} maxLength={1000} placeholder="e.g. What is your return policy?" className="min-h-10 min-w-0 flex-1 rounded-lg border border-slate-200 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30"/>
            <Button type="button" variant="secondary" disabled={!sampleRoutingMessage.trim() || agents.isPending || agents.isError || selectedAgents.length === 0 || routingPreview.isPending} onClick={() => routingPreview.mutate({ message: sampleRoutingMessage.trim(), ai_agent_ids: selectedAgents })}>{routingPreview.isPending ? "Checking…" : "Preview"}</Button>
          </div>
          {routingPreview.data && <p role="status" className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-900">“{routingPreview.variables?.message}” would go to <strong>{routingPreview.data.ai_agent_name}</strong>. {routingPreviewReason(routingPreview.data.routing_reason, routingPreview.data.matched_bot_count)} This is a routing preview, not a generated answer.</p>}
          {routingPreview.isError && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-800">Routing could not be previewed. Check the selected active bots and try again.</p>}
        </div>}
        <label className="flex items-center gap-2 text-sm text-slate-700"><Checkbox checked={aiEnabled} onCheckedChange={(checked) => setAiEnabledDraft(checked === true)}/>Enable AI replies</label>
        <label className="block space-y-1 text-sm text-slate-700"><span>Reply mode</span><Select aria-label="AI reply mode" value={aiReplyMode} disabled={!aiEnabled} onChange={(event) => setAiModeDraft(event.target.value as "draft_only" | "auto_reply")} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2"><option value="draft_only">Draft only · teammate reviews and sends</option><option value="auto_reply">Auto reply · send safe replies and grounded answers</option></Select></label>
        {!aiEnabled && <p className="text-xs text-slate-500">Disabled by default. Turn this on to start processing new widget messages.</p>}
        {aiEnabled && aiReplyMode === "draft_only" && <p className="text-xs text-slate-500">AI drafts appear in the inbox. Nothing is sent automatically.</p>}
        {aiEnabled && aiReplyMode === "auto_reply" && <p className="text-xs font-medium text-amber-800">Greetings and safe next steps can be answered automatically. Store-specific answers require published knowledge; order details require shopper verification, and order changes require human review.</p>}
      </section>
      {save.isError && <p role="alert" className="text-sm text-red-700">{save.error instanceof ApiError ? save.error.message : "Widget settings could not be saved."}</p>}
      <Button type="button" disabled={config.isPending || config.isError || agents.isPending || agents.isError || save.isPending || origins.length === 0 || selectedAgents.length === 0 || !assistantName.trim() || !welcomeMessage.trim()} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : config.data ? "Save widget settings" : "Create storefront widget"}</Button>
      {save.isSuccess && <p role="status" className="text-sm text-emerald-700">Widget settings saved.</p>}
      {config.data && <div className="space-y-2 border-t border-slate-100 pt-4"><div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">Shopify theme embed</h3><Button size="sm" variant="secondary" onClick={copySnippet}>{copied ? <Check size={14}/> : <Copy size={14}/>} {copied ? "Copied" : "Copy snippet"}</Button></div><pre className="overflow-x-auto rounded-xl bg-slate-950 p-3 text-xs leading-5 text-slate-100"><code>{embed || "Set NEXT_PUBLIC_SUPPORTPILOT_APP_URL to the public app URL before installing outside localhost."}</code></pre><p className="text-xs leading-5 text-slate-500">In Shopify Admin, open **Online Store → Themes → Edit code**, paste this before <code>&lt;/body&gt;</code> in <code>layout/theme.liquid</code>, and save. Replace any older SupportPilot script tag with this versioned snippet so the browser loads the latest widget. For a local app, use an HTTPS tunnel URL in <code>NEXT_PUBLIC_SUPPORTPILOT_APP_URL</code>; localhost is not reachable from Shopify shoppers.</p><p className="text-xs text-slate-500">Widget ID: <code>{config.data.public_id}</code></p></div>}
    </PanelBody>
  </Panel>;
}

function routingPreviewReason(reason: WidgetRoutingPreview["routing_reason"], matchedBotCount: number): string {
  if (reason === "best_source_match") {
    return `Its assigned knowledge matched best; ${matchedBotCount} eligible ${matchedBotCount === 1 ? "bot has" : "bots have"} matching sources.`;
  }
  if (reason === "conversation_continuity") return "No stronger source match was found, so the conversation’s current bot stays selected.";
  if (reason === "conversation_override") return "A teammate pinned this bot for the conversation.";
  return "No selected bot had a matching assigned source, so the primary fallback bot was selected.";
}
