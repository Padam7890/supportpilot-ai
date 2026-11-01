"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, MessageCircle, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ApiError } from "@/lib/api/errors";
import { createWidgetConfig, getWidgetConfig, updateWidgetConfig, widgetConfigKey } from "../api/widget-api";

export function StorefrontWidgetCard() {
  const client = useQueryClient();
  const config = useQuery({ queryKey: widgetConfigKey, queryFn: getWidgetConfig });
  const [originsDraft, setOriginsDraft] = useState<string>();
  const [enabledDraft, setEnabledDraft] = useState<boolean>();
  const [aiEnabledDraft, setAiEnabledDraft] = useState<boolean>();
  const [aiModeDraft, setAiModeDraft] = useState<"draft_only" | "auto_reply">();
  const [copied, setCopied] = useState(false);
  const appBase = (process.env.NEXT_PUBLIC_SUPPORTPILOT_APP_URL || (typeof window !== "undefined" ? window.location.origin : "")).replace(/\/$/, "");
  const widgetScriptVersion = "2026-11-01-recommendations-v1";
  const originsText = originsDraft ?? config.data?.allowed_origins.join("\n") ?? "";
  const enabled = enabledDraft ?? config.data?.enabled ?? true;
  const aiEnabled = aiEnabledDraft ?? config.data?.ai_enabled ?? false;
  const aiReplyMode = aiModeDraft ?? config.data?.ai_reply_mode ?? "draft_only";
  const origins = useMemo(() => originsText.split(/[\n,]/).map((value) => value.trim()).filter(Boolean), [originsText]);
  const save = useMutation({
    mutationFn: () => config.data
      ? updateWidgetConfig({ allowed_origins: origins, enabled, collect_contact: config.data.collect_contact, ai_enabled: aiEnabled, ai_reply_mode: aiReplyMode })
      : createWidgetConfig({ allowed_origins: origins, ai_enabled: aiEnabled, ai_reply_mode: aiReplyMode }),
    onSuccess: async (saved) => {
      client.setQueryData(widgetConfigKey, saved);
      setOriginsDraft(undefined);
      setEnabledDraft(undefined);
      setAiEnabledDraft(undefined);
      setAiModeDraft(undefined);
      await client.invalidateQueries({ queryKey: widgetConfigKey });
    },
  });
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
      <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Allowed storefront origins</span><textarea aria-label="Allowed storefront origins" value={originsText} onChange={(event) => setOriginsDraft(event.target.value)} placeholder="https://your-store.myshopify.com" rows={3} className="w-full rounded-xl border border-slate-200 bg-white p-3 text-sm outline-none focus:border-blue-500"/><span className="block text-xs font-normal text-slate-500">One exact origin per line, including https://. Add your Shopify storefront domain.</span></label>
      {config.data && <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={enabled} onChange={(event) => setEnabledDraft(event.target.checked)}/>Widget enabled</label>}
      <section className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4" aria-labelledby="widget-ai-title">
        <div><h3 id="widget-ai-title" className="text-sm font-semibold text-slate-900">AI replies</h3><p className="mt-1 text-xs leading-5 text-slate-600">AI uses your published knowledge articles. Order, refund, cancellation, account, and unsupported questions go to a teammate.</p></div>
        <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={aiEnabled} onChange={(event) => setAiEnabledDraft(event.target.checked)}/>Enable AI replies</label>
        <label className="block space-y-1 text-sm text-slate-700"><span>Reply mode</span><select aria-label="AI reply mode" value={aiReplyMode} disabled={!aiEnabled} onChange={(event) => setAiModeDraft(event.target.value as "draft_only" | "auto_reply")} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2"><option value="draft_only">Draft only · teammate reviews and sends</option><option value="auto_reply">Auto reply · send safe replies and grounded answers</option></select></label>
        {!aiEnabled && <p className="text-xs text-slate-500">Disabled by default. Turn this on to start processing new widget messages.</p>}
        {aiEnabled && aiReplyMode === "draft_only" && <p className="text-xs text-slate-500">AI drafts appear in the inbox. Nothing is sent automatically.</p>}
        {aiEnabled && aiReplyMode === "auto_reply" && <p className="text-xs font-medium text-amber-800">Greetings and safe next steps can be answered automatically. Store-specific answers require published knowledge; order details require shopper verification, and order changes require human review.</p>}
      </section>
      {save.isError && <p role="alert" className="text-sm text-red-700">{save.error instanceof ApiError ? save.error.message : "Widget settings could not be saved."}</p>}
      <Button type="button" disabled={config.isPending || config.isError || save.isPending || origins.length === 0} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : config.data ? "Save widget settings" : "Create storefront widget"}</Button>
      {save.isSuccess && <p role="status" className="text-sm text-emerald-700">Widget settings saved.</p>}
      {config.data && <div className="space-y-2 border-t border-slate-100 pt-4"><div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">Shopify theme embed</h3><Button size="sm" variant="secondary" onClick={copySnippet}>{copied ? <Check size={14}/> : <Copy size={14}/>} {copied ? "Copied" : "Copy snippet"}</Button></div><pre className="overflow-x-auto rounded-xl bg-slate-950 p-3 text-xs leading-5 text-slate-100"><code>{embed || "Set NEXT_PUBLIC_SUPPORTPILOT_APP_URL to the public app URL before installing outside localhost."}</code></pre><p className="text-xs leading-5 text-slate-500">In Shopify Admin, open **Online Store → Themes → Edit code**, paste this before <code>&lt;/body&gt;</code> in <code>layout/theme.liquid</code>, and save. Replace any older SupportPilot script tag with this versioned snippet so the browser loads the latest widget. For a local app, use an HTTPS tunnel URL in <code>NEXT_PUBLIC_SUPPORTPILOT_APP_URL</code>; localhost is not reachable from Shopify shoppers.</p><p className="text-xs text-slate-500">Widget ID: <code>{config.data.public_id}</code></p></div>}
    </PanelBody>
  </Panel>;
}
