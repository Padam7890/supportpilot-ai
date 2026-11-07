"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MessageCircle, Send, X } from "lucide-react";
import { aiAgentsKey, listAIAgents } from "@/features/ai/api/ai-agent-api";
import { getWidgetConfig, widgetConfigKey } from "@/features/integrations/api/widget-api";
import type { WidgetPreviewDraft } from "../types/widget-preview";

export function WidgetPreview({ draftSettings }: { draftSettings?: WidgetPreviewDraft }) {
  const [isOpen, setIsOpen] = useState(true);
  const config = useQuery({ queryKey: widgetConfigKey, queryFn: getWidgetConfig });
  const agents = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents });
  const configuredAgentIds = config.data?.ai_agent_ids?.length
    ? config.data.ai_agent_ids
    : config.data?.ai_agent_id
      ? [config.data.ai_agent_id]
      : [];
  const configuredAgents = agents.data?.items.filter((agent) =>
    agent.status === "active" && configuredAgentIds.includes(agent.id),
  ) ?? [];
  const widgetEnabled = draftSettings?.enabled ?? config.data?.enabled;
  const aiEnabled = draftSettings?.aiEnabled ?? config.data?.ai_enabled;
  const replyMode = draftSettings?.replyMode ?? config.data?.ai_reply_mode;
  const botNames = draftSettings?.botNames ?? configuredAgents.map((agent) => agent.name);

  return <section aria-label="Storefront chat widget preview" className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 sm:px-6">
      <div>
        <h2 className="font-semibold text-slate-900">Storefront preview</h2>
        <p className="mt-1 text-sm text-slate-500">Updates as you edit the launcher, reply mode, and selected AI bots.</p>
      </div>
      <button type="button" onClick={() => setIsOpen((value) => !value)} aria-pressed={isOpen} className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
        {isOpen ? "Preview launcher" : "Open preview"}
      </button>
    </div>

    {config.isSuccess && widgetEnabled === false && <p role="status" className="border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-900">The storefront widget is disabled. This preview is illustrative and will not appear to shoppers.</p>}

    <div className="relative min-h-[560px] overflow-hidden bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-blue-50 via-slate-50 to-slate-100 p-5 sm:p-8">
      <div aria-hidden="true" className="mx-auto max-w-3xl space-y-5 opacity-70">
        <div className="flex items-center justify-between rounded-2xl border border-white/80 bg-white/80 px-5 py-4 shadow-sm">
          <div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-blue-700 text-sm font-bold text-white">S</span><span className="font-semibold text-slate-800">Your storefront</span></div>
          <div className="hidden gap-5 text-sm text-slate-500 sm:flex"><span>Shop</span><span>Collections</span><span>About</span></div>
        </div>
        <div className="rounded-2xl border border-white/80 bg-white/70 p-6 shadow-sm sm:p-10">
          <div className="h-3 w-24 rounded-full bg-blue-100"/><div className="mt-5 h-7 w-2/3 rounded-lg bg-slate-200"/><div className="mt-3 h-4 w-1/2 rounded-lg bg-slate-100"/>
          <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3"><div className="aspect-[4/3] rounded-xl bg-gradient-to-br from-indigo-100 to-slate-200"/><div className="aspect-[4/3] rounded-xl bg-gradient-to-br from-amber-100 to-orange-100"/><div className="hidden aspect-[4/3] rounded-xl bg-gradient-to-br from-emerald-100 to-teal-100 sm:block"/></div>
        </div>
      </div>

      <div className="absolute bottom-5 right-5 z-10 flex flex-col items-end gap-3 sm:bottom-8 sm:right-8">
        {isOpen && <section role="dialog" aria-label="SupportPilot chat preview" className="flex h-[430px] w-[min(370px,calc(100vw-3rem))] flex-col overflow-hidden rounded-3xl border border-slate-200 bg-[#f8faff] shadow-[0_24px_70px_rgba(30,48,90,0.24)]">
          <header className="flex items-center gap-3 bg-gradient-to-r from-blue-700 to-indigo-700 px-4 py-4 text-white">
            <span className="grid size-10 place-items-center rounded-2xl border border-white/30 bg-white/15 font-bold">S</span>
            <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">Your store</p><p className="text-xs text-blue-100">SupportPilot AI</p><p className="mt-1 flex items-center gap-1.5 text-[11px] text-blue-100"><span className="size-1.5 rounded-full bg-emerald-300"/>Chat available</p></div>
            <button type="button" onClick={() => setIsOpen(false)} aria-label="Close widget preview" className="grid size-9 place-items-center rounded-xl bg-white/15 hover:bg-white/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"><X size={18}/></button>
          </header>
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm"><p className="text-sm font-semibold text-slate-800">Hi! Welcome to our store.</p><p className="mt-1 text-xs leading-5 text-slate-600">I’m here to help with products, orders, and any questions you have.</p></div>
            <div className="flex flex-wrap gap-2"><span className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700">Track an order</span><span className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700">Product questions</span></div>
            <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-blue-700 px-3.5 py-2.5 text-sm text-white">Can you help me find something?</div>
            <div className="max-w-[88%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-3.5 py-2.5 text-sm leading-5 text-slate-700 shadow-sm">Of course! Tell me what you’re looking for and I’ll help you find the right option.</div>
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/80 p-3 text-xs leading-5 text-indigo-950">
              <p className="font-semibold">AI routing preview</p>
              {config.isPending || agents.isPending ? <p role="status" className="mt-1 text-indigo-800">Loading widget settings…</p> : config.isError || agents.isError ? <p role="alert" className="mt-1 text-rose-800">Bot routing could not be loaded. Check the widget settings panel.</p> : widgetEnabled === false ? <p className="mt-1 text-indigo-800">The widget is disabled, so AI replies are inactive.</p> : aiEnabled ? <>
                <p className="mt-1">{replyMode === "auto_reply" ? "Auto reply is enabled." : "AI drafts are reviewed by your team before sending."} Messages route to the best-matching selected bot.</p>
                {botNames.length > 0 ? <p className="mt-2 font-medium">Available bots: {botNames.join(", ")}</p> : <p className="mt-2 text-amber-800">No active bot is selected for widget replies.</p>}
              </> : <p className="mt-1 text-indigo-800">AI replies are disabled in the current widget settings.</p>}
            </div>
            <p className="px-1 text-[10px] text-slate-400">Preview only · no message is sent</p>
          </div>
          <div className="flex items-center gap-2 border-t border-slate-200 bg-white p-3"><div className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-400">Ask us anything…</div><span className="grid size-10 place-items-center rounded-xl bg-blue-700 text-white"><Send size={16}/></span></div>
          <div className="flex justify-between bg-white px-4 pb-3 text-[10px] text-slate-400"><span>Powered by SupportPilot AI</span><span>Replies may be reviewed</span></div>
        </section>}
        <button type="button" onClick={() => setIsOpen((value) => !value)} aria-expanded={isOpen} className="flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-700 to-indigo-700 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-900/20 transition hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"><MessageCircle size={18}/>{isOpen ? "Chat with us" : "Open chat"}</button>
      </div>
    </div>
  </section>;
}
