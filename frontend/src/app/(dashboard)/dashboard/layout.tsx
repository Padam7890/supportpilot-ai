import type { ReactNode } from "react";
import { Suspense } from "react";
import { DashboardShell } from "@/components/dashboard-shell";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="grid min-h-screen place-items-center bg-slate-50 text-sm text-slate-500">Loading workspace…</div>}>
      <DashboardShell>{children}</DashboardShell>
    </Suspense>
  );
}
