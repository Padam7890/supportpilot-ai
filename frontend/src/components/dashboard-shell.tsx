"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppSidebar } from "@/components/app-sidebar";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { getCurrentUser, currentUserQueryKey, logout as logoutRequest } from "@/features/auth/api/auth-api";
import { getOperationalAlerts, analyticsQueryKeys } from "@/features/analytics/api/analytics-api";
import { getSystemReadiness, getWorkerHealth } from "@/features/dashboard/api/system-status-api";
import { getInbox } from "@/features/inbox/api/inbox-api";
import type { InboxFilters } from "@/features/inbox/api/inbox-api";
import { ensureTypographyScaleFromStorage } from "@/lib/typography-scale";

const sidebarUnreadFilters: InboxFilters = {
  scope: "all",
  status: "",
  priority: "",
  search: "",
  needsApproval: false,
  unreadOnly: true,
};

function subscribeTheme(callback: () => void) {
  window.addEventListener("supportpilot-theme-change", callback);
  return () => window.removeEventListener("supportpilot-theme-change", callback);
}

function getThemeSnapshot() {
  return document.documentElement.dataset.theme === "dark";
}

function getThemeServerSnapshot() {
  return false;
}

function subscribeSidebar(callback: () => void) {
  window.addEventListener("supportpilot-sidebar-change", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener("supportpilot-sidebar-change", callback);
    window.removeEventListener("storage", callback);
  };
}

function getSidebarSnapshot() {
  return window.localStorage.getItem("supportpilot-sidebar-collapsed") === "true";
}

function getSidebarServerSnapshot() {
  return false;
}

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const sidebarCollapsed = useSyncExternalStore(subscribeSidebar, getSidebarSnapshot, getSidebarServerSnapshot);
  const dark = useSyncExternalStore(subscribeTheme, getThemeSnapshot, getThemeServerSnapshot);
  const me = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const readiness = useQuery({
    queryKey: ["system-readiness"],
    queryFn: getSystemReadiness,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
  const worker = useQuery({
    queryKey: ["worker-health"],
    queryFn: getWorkerHealth,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 15_000 : false,
    refetchIntervalInBackground: false,
  });
  const alerts = useQuery({
    queryKey: analyticsQueryKeys.operationalAlerts(),
    queryFn: getOperationalAlerts,
    enabled: Boolean(me.data),
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 60_000 : false,
    refetchIntervalInBackground: false,
  });
  const unread = useQuery({
    queryKey: ["sidebar-unread-inbox"],
    queryFn: () => getInbox(sidebarUnreadFilters),
    enabled: Boolean(me.data),
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
  const logout = useMutation({
    mutationFn: logoutRequest,
    onSettled: () => {
      queryClient.clear();
      router.replace("/login");
    },
  });

  useEffect(() => {
    if (me.isError) router.replace("/login");
  }, [me.isError, router]);

  useEffect(() => {
    const saved = window.localStorage.getItem("supportpilot-theme");
    const enabled = saved === "dark";
    document.documentElement.dataset.theme = enabled ? "dark" : "light";
    document.documentElement.classList.toggle("dark", enabled);
    window.dispatchEvent(new Event("supportpilot-theme-change"));
    ensureTypographyScaleFromStorage();
  }, []);

  function toggleSidebar() {
    window.localStorage.setItem("supportpilot-sidebar-collapsed", String(!sidebarCollapsed));
    window.dispatchEvent(new Event("supportpilot-sidebar-change"));
  }

  function toggleTheme() {
    const enabled = !dark;
    document.documentElement.dataset.theme = enabled ? "dark" : "light";
    document.documentElement.classList.toggle("dark", enabled);
    window.localStorage.setItem("supportpilot-theme", enabled ? "dark" : "light");
    window.dispatchEvent(new Event("supportpilot-theme-change"));
  }

  if (me.isPending || !me.data) {
    return <div className="grid min-h-screen place-items-center bg-background text-foreground"><div role="status" className="flex items-center gap-3 text-sm text-muted-foreground"><span className="size-5 animate-spin rounded-full border-2 border-primary/20 border-t-primary"/>Loading your workspace…</div></div>;
  }

  const unreadCount = unread.data?.items.length ?? 0;
  const hasMoreUnread = Boolean(unread.data?.nextCursor);
  const workerState = worker.isPending ? "checking" : worker.isError ? "unavailable" : worker.data.status === "active" ? "online" : "offline";
  const serviceState = readiness.isPending ? "checking" : readiness.isError ? "unavailable" : "ready";

  return <div className="min-h-dvh bg-background text-foreground">
    <div className={`fixed inset-y-0 left-0 z-30 hidden h-dvh transition-[width] duration-150 lg:block ${sidebarCollapsed ? "w-14" : "w-[248px]"}`}>
      <AppSidebar
        user={me.data}
        collapsed={sidebarCollapsed}
        unreadCount={unreadCount}
        hasMoreUnread={hasMoreUnread}
        onToggleCollapse={toggleSidebar}
        onOpenSearch={() => setSearchOpen(true)}
        onSwitchWorkspace={() => logout.mutate()}
      />
    </div>
    <div className={`min-w-0 transition-[padding] duration-150 ${sidebarCollapsed ? "lg:pl-14" : "lg:pl-[248px]"}`}>
      <DashboardTopbar
        pathname={pathname}
        user={me.data}
        alerts={alerts.data}
        alertsUnavailable={alerts.isError}
        serviceState={serviceState}
        workerState={workerState}
        workerCount={worker.data?.active_workers}
        dark={dark}
        mobileOpen={mobileOpen}
        searchOpen={searchOpen}
        unreadCount={unreadCount}
        hasMoreUnread={hasMoreUnread}
        onMobileOpenChange={setMobileOpen}
        onSearchOpenChange={setSearchOpen}
        onToggleTheme={toggleTheme}
        onSignOut={() => logout.mutate()}
      />
      <main className={pathname.startsWith("/dashboard/inbox") || pathname.startsWith("/dashboard/automations") ? "h-[calc(100dvh-3.25rem)] w-full overflow-hidden p-0" : "mx-auto w-full max-w-[1440px] p-3 sm:p-5 lg:p-6"}>
        {children}
      </main>
    </div>
  </div>;
}
