"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AutomationHub } from "@/features/automations/components/automation-hub";
import { AutomationWorkspace } from "@/features/automations/components/automation-workspace";

function AutomationsContent() {
  const searchParams = useSearchParams();
  const edit = searchParams.get("edit");

  if (edit !== null) {
    return <AutomationWorkspace />;
  }

  return <AutomationHub />;
}

export default function AutomationsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center bg-slate-50 p-8">
          <p className="text-sm text-slate-500">Loading automations…</p>
        </div>
      }
    >
      <AutomationsContent />
    </Suspense>
  );
}
