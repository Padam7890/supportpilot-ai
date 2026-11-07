"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Building2, CircleHelp, LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Sun, X } from "lucide-react";
import { getCurrentUser, currentUserQueryKey, logout as logoutRequest } from "@/features/auth/api/auth-api";
import { getSystemReadiness, getWorkerHealth } from "@/features/dashboard/api/system-status-api";
import { Button } from "@/components/ui/button";
import { CommandSearch } from "@/features/search/components/command-search";
import {
  getDashboardNavigation,
  isDashboardNavigationLinkActive,
} from "@/features/dashboard/navigation/dashboard-navigation";
import { ensureTypographyScaleFromStorage } from "@/lib/typography-scale";

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
  const isInbox = pathname.startsWith("/dashboard/inbox");
  const isFullBleed = isInbox || pathname.startsWith("/dashboard/automations");
  const router = useRouter();
  const queryClient = useQueryClient();
  const [mobileOpen, setMobileOpen] = useState(false);
  const sidebarCollapsed = useSyncExternalStore(subscribeSidebar, getSidebarSnapshot, getSidebarServerSnapshot);
  const dark = useSyncExternalStore(subscribeTheme, getThemeSnapshot, getThemeServerSnapshot);
  const desktopSidebarOffset = sidebarCollapsed
    ? isInbox ? "md:pl-[72px]" : "lg:pl-[72px]"
    : isInbox
      ? "md:pl-[72px] lg:pl-64"
      : "lg:pl-64";
  const me = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const readiness = useQuery({
    queryKey: ["system-readiness"],
    queryFn: getSystemReadiness,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
  const workerHealth = useQuery({
    queryKey: ["worker-health"],
    queryFn: getWorkerHealth,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 15_000 : false,
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
    return <div className="grid min-h-screen place-items-center bg-slate-50"><div className="space-y-3 text-center"><div className="mx-auto size-9 animate-spin rounded-full border-4 border-blue-100 border-t-blue-700"/><p className="text-sm text-slate-500">Loading your workspace…</p></div></div>;
  }
  const user = me.data;
  const navigationGroups = getDashboardNavigation(user.role);

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      {mobileOpen && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-slate-950/40 lg:hidden" onClick={() => setMobileOpen(false)} />}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex h-dvh max-h-dvh w-64 flex-col overflow-hidden border-r border-slate-200 bg-white shadow-xl transition-all duration-200 ${isInbox ? "md:translate-x-0" : "lg:translate-x-0"} lg:shadow-none ${sidebarCollapsed ? isInbox ? "md:w-[72px]" : "lg:w-[72px]" : isInbox ? "md:w-[72px] lg:w-64" : "lg:w-64"} ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className={`flex h-14 shrink-0 items-center gap-2 ${sidebarCollapsed ? "justify-center px-3" : isInbox ? "px-4 md:justify-center md:px-3 lg:justify-start lg:px-4" : "px-4"}`}>
          <span className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-blue-700 text-sm font-black text-white">S</span>
          {!sidebarCollapsed && (
            <span className={`min-w-0 ${isInbox ? "md:hidden lg:block" : ""}`}>
              <span className="sidebar-brand block">SupportPilot AI</span>
              <span className="sidebar-brand-tagline block">Professional workspace</span>
            </span>
          )}
          <button className={`ml-auto rounded-lg p-2 text-slate-500 hover:bg-slate-100 ${isInbox ? "md:hidden" : "lg:hidden"}`} onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={18}/></button>
          <button type="button" onClick={toggleSidebar} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} className="ml-auto hidden size-9 shrink-0 place-items-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 lg:grid">{sidebarCollapsed ? <PanelLeftOpen size={18}/> : <PanelLeftClose size={18}/>}</button>
        </div>
        {!sidebarCollapsed && (
          <div className={`mx-3 mb-3 shrink-0 rounded-xl bg-slate-50 p-2.5 ${isInbox ? "md:hidden lg:block" : ""}`}>
            <div className="sidebar-group flex items-center gap-1.5">
              <Building2 size={12} aria-hidden /> Workspace
            </div>
            <p className="sidebar-workspace mt-1.5 truncate">{user.organization?.name ?? "Your organization"}</p>
            <p className="meta-text mt-0.5 truncate">{user.organization?.slug}</p>
          </div>
        )}
        <nav
          aria-label="Main navigation"
          className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-y-contain px-3 pb-2 [-webkit-overflow-scrolling:touch]"
        >
          {navigationGroups.map((group) => (
            <div key={group.label} role="group" aria-label={group.label} className="space-y-0.5">
              {!sidebarCollapsed && (
                <p
                  className={`sidebar-group sticky top-0 z-[1] bg-white px-2 pb-1 pt-1 ${isInbox ? "md:hidden lg:block" : ""}`}
                >
                  {group.label}
                </p>
              )}
              {group.links.map(({ href, label, icon: Icon, exact }) => {
                const active = isDashboardNavigationLinkActive(pathname, { href, label, icon: Icon, exact });
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setMobileOpen(false)}
                    title={sidebarCollapsed || isInbox ? label : undefined}
                    aria-label={sidebarCollapsed || isInbox ? label : undefined}
                    aria-current={active ? "page" : undefined}
                    className={`sidebar-item flex min-h-[36px] items-center gap-2.5 rounded-lg px-2 py-2 transition ${sidebarCollapsed ? "justify-center" : isInbox ? "md:justify-center lg:justify-start" : ""} ${active ? "bg-blue-50 font-medium text-blue-800" : "hover:bg-slate-50 hover:text-[var(--text-primary)]"}`}
                  >
                    <Icon size={17} className="shrink-0" strokeWidth={active ? 2.25 : 2} />
                    {!sidebarCollapsed && <span className={`min-w-0 flex-1 truncate ${isInbox ? "md:hidden lg:block" : ""}`}>{label}</span>}
                    {!sidebarCollapsed && active && (
                      <span className={`size-1.5 shrink-0 rounded-full bg-blue-700 ${isInbox ? "md:hidden lg:block" : ""}`} />
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="shrink-0 border-t border-slate-100 p-3">
          {!sidebarCollapsed && <div className={`mb-3 flex items-center gap-2 px-2 text-xs text-slate-600 ${isInbox ? "md:hidden lg:flex" : ""}`}><CircleHelp size={15}/> Need a hand? <span className="ml-auto text-slate-600">v0.3</span></div>}
          <div className={`flex items-center rounded-xl p-2 ${sidebarCollapsed ? "justify-center" : isInbox ? "gap-3 md:flex-col md:gap-1 lg:flex-row lg:gap-3" : "gap-3"}`}>
            <div title={sidebarCollapsed ? user.full_name : undefined} className="grid size-9 shrink-0 place-items-center rounded-full bg-blue-100 text-sm font-bold text-blue-800">{user.full_name.slice(0, 1).toUpperCase()}</div>
            {!sidebarCollapsed && <div className={`min-w-0 flex-1 ${isInbox ? "md:hidden lg:block" : ""}`}><p className="truncate text-sm font-semibold">{user.full_name}</p><p className="truncate text-xs capitalize text-slate-500">{user.role}</p></div>}
            <button title="Sign out" onClick={() => logout.mutate()} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" aria-label="Sign out"><LogOut size={17}/></button>
          </div>
        </div>
      </aside>
      <div className={`min-w-0 flex-1 ${desktopSidebarOffset}`}>
        <header className="sticky top-0 z-20 flex h-12 items-center justify-between border-b border-slate-200 bg-white/90 px-3 backdrop-blur sm:px-6">
          <div className="flex items-center gap-2"><button aria-label="Open navigation" onClick={() => setMobileOpen(true)} className={`rounded-xl p-2 text-slate-600 hover:bg-slate-100 ${isInbox ? "md:hidden" : "lg:hidden"}`}><Menu size={20}/></button><button type="button" onClick={toggleSidebar} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} className="hidden rounded-xl p-2 text-slate-600 hover:bg-slate-100 lg:inline-flex">{sidebarCollapsed ? <PanelLeftOpen size={20}/> : <PanelLeftClose size={20}/>}</button></div>
          <div role="status" aria-live="polite" className="hidden items-center gap-2 text-xs text-slate-500 sm:flex">
            <Activity size={14} className={readiness.isSuccess ? "text-emerald-500" : readiness.isError ? "text-amber-500" : "animate-pulse text-slate-400"}/>
            {readiness.isSuccess ? "Core services ready" : readiness.isError ? "System status unavailable" : "Checking system status…"}
            {workerHealth.isSuccess && <span className={`ml-2 border-l border-slate-200 pl-3 text-xs ${workerHealth.data.status === "active" ? "text-emerald-700" : "text-amber-700"}`} title={`Active durable workers: ${workerHealth.data.active_workers}`}>
              {workerHealth.data.status === "active" ? `Worker${workerHealth.data.active_workers === 1 ? "" : "s"} online` : "Worker offline"}
            </span>}
            {workerHealth.isError && <span className="ml-2 border-l border-slate-200 pl-3 text-xs text-amber-700" title="Worker heartbeat could not be checked">Worker status unavailable</span>}
          </div>
          <div className="ml-3"><CommandSearch/></div>
          <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
            <span className="hidden text-xs text-slate-500 md:block">{user.email}</span>
            <button onClick={toggleTheme} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100">{dark ? <Sun size={16}/> : <Moon size={16}/>}</button>
            <Button size="sm" variant="ghost" onClick={() => logout.mutate()}>Sign out</Button>
          </div>
        </header>
        <main className={isFullBleed ? "h-[calc(100dvh-3rem)] w-full overflow-hidden p-0" : "mx-auto w-full max-w-7xl p-3 sm:p-5 lg:p-6"}>{children}</main>
      </div>
    </div>
  );
}
