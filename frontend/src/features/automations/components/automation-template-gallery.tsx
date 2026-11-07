"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { automationKey, listAutomationTemplates } from "../api/automation-api";

export function AutomationTemplateGallery() {
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const canManage = me.data?.role === "owner" || me.data?.role === "admin";
  const templates = useQuery({ queryKey: [...automationKey, "templates"], queryFn: () => listAutomationTemplates() });

  return (
    <div className="h-full overflow-y-auto bg-slate-50">
      <header className="border-b border-slate-200 bg-white px-4 py-5 sm:px-8">
        <div className="mx-auto flex max-w-5xl flex-wrap items-end justify-between gap-4">
          <div>
            <Link
              href="/dashboard/automations"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800"
            >
              <ArrowLeft size={14} aria-hidden />
              Back to workflows
            </Link>
            <p className="mt-3 text-xs font-medium uppercase tracking-wide text-slate-500">Automations</p>
            <h1 className="mt-0.5 text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">Template gallery</h1>
            <p className="mt-1.5 max-w-xl text-sm text-slate-600">Start from a curated playbook or open a blank workflow in the builder.</p>
          </div>
          {canManage && (
            <Link href="/dashboard/automations?edit=new">
              <Button type="button" variant="secondary" className="border-slate-200">
                <Plus size={16} /> Blank workflow
              </Button>
            </Link>
          )}
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-5 sm:px-8">
        {templates.isPending ? (
          <p className="text-sm text-slate-500" role="status">
            Loading templates…
          </p>
        ) : templates.isError ? (
          <p className="text-sm text-red-700">Could not load templates.</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {(templates.data ?? []).map((t) => (
              <li key={t.id} className="rounded-lg border border-slate-200 bg-white p-3 sm:p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900">{t.title}</p>
                    <p className="mt-1 text-xs text-slate-600">{t.description}</p>
                    <p className="mt-2 text-[10px] uppercase tracking-wide text-slate-500">
                      {t.category}
                      {!t.available && t.missing_capabilities.length > 0
                        ? ` · needs ${t.missing_capabilities.join(", ")}`
                        : ""}
                    </p>
                  </div>
                  {canManage ? (
                    t.available ? (
                      <Link href={`/dashboard/automations?edit=new&template=${encodeURIComponent(t.id)}`}>
                        <Button type="button" size="sm" className="shrink-0 bg-teal-700 hover:bg-teal-800">
                          Use template
                        </Button>
                      </Link>
                    ) : (
                      <span className="text-[11px] font-medium text-slate-500">Unavailable</span>
                    )
                  ) : (
                    <span className="text-[11px] text-slate-500">Admin only</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
