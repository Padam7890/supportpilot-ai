"use client";

import { useState } from "react";
import { MessageCircle, ShieldCheck } from "lucide-react";
import { StorefrontWidgetCard } from "@/features/integrations/components/storefront-widget-card";
import { WidgetPreview } from "./widget-preview";
import type { WidgetPreviewDraft } from "../types/widget-preview";

export function WidgetWorkspace() {
  const [previewDraft, setPreviewDraft] = useState<WidgetPreviewDraft>();

  return <div className="space-y-7">
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div><p className="flex items-center gap-2 text-sm font-semibold text-blue-700"><MessageCircle size={16}/> Customer experience</p><h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-950">Chat widget</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Preview how customers see SupportPilot on your storefront, then configure its installation and reply behavior.</p></div>
      <p className="flex items-center gap-2 rounded-xl bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-800"><ShieldCheck size={15}/> Preview messages are not sent</p>
    </header>
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
      <WidgetPreview draftSettings={previewDraft}/>
      <div className="min-w-0"><StorefrontWidgetCard onPreviewChange={setPreviewDraft}/></div>
    </div>
  </div>;
}
