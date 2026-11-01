"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, BarChart3, BookOpen, Building2, CircleHelp, Inbox, LogOut, Menu, Moon, PackageSearch, PanelLeftClose, PanelLeftOpen, ShieldCheck, Sparkles, Sun, Users, X } from "lucide-react";
import { getCurrentUser, currentUserQueryKey, logout as logoutRequest } from "@/features/auth/api/auth-api";
import { getSystemReadiness } from "@/features/dashboard/api/system-status-api";
import { Button } from "@/components/ui/button";
import { CommandSearch } from "@/features/search/components/command-search";

const navigation = [
  { href: "/dashboard", label: "Overview", icon: BarChart3, exact: true },
  { href: "/dashboard/inbox", label: "Inbox", icon: Inbox },
  { href: "/dashboard/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/dashboard/ai", label: "AI Playground", icon: Sparkles },
  { href: "/dashboard/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/dashboard/operations", label: "Operations", icon: Activity },
  { href: "/dashboard/security", label: "Security", icon: ShieldCheck },
  { href: "/dashboard/orders", label: "Shopify orders", icon: PackageSearch },
  { href: "/dashboard/tickets", label: "Tickets", icon: Inbox },
  { href: "/dashboard/customers", label: "Customers", icon: Users },
];

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
  const router = useRouter();
  const queryClient = useQueryClient();
  const [mobileOpen, setMobileOpen] = useState(false);
  const sidebarCollapsed = useSyncExternalStore(subscribeSidebar, getSidebarSnapshot, getSidebarServerSnapshot);
  const dark = useSyncExternalStore(subscribeTheme, getThemeSnapshot, getThemeServerSnapshot);
  const me = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const readiness = useQuery({
    queryKey: ["system-readiness"],
    queryFn: getSystemReadiness,
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
    window.dispatchEvent(new Event("supportpilot-theme-change"));
  }, []);

  function toggleSidebar() {
    window.localStorage.setItem("supportpilot-sidebar-collapsed", String(!sidebarCollapsed));
    window.dispatchEvent(new Event("supportpilot-sidebar-change"));
  }

  function toggleTheme() {
    const enabled = !dark;
    document.documentElement.dataset.theme = enabled ? "dark" : "light";
    window.localStorage.setItem("supportpilot-theme", enabled ? "dark" : "light");
    window.dispatchEvent(new Event("supportpilot-theme-change"));
  }

  if (me.isPending || !me.data) {
    return <div className="grid min-h-screen place-items-center bg-slate-50"><div className="space-y-3 text-center"><div className="mx-auto size-9 animate-spin rounded-full border-4 border-blue-100 border-t-blue-700"/><p className="text-sm text-slate-500">Loading your workspace…</p></div></div>;
  }
  const user = me.data;
  const canManage = user.role === "owner" || user.role === "admin";
  const links = canManage ? [...navigation, { href: "/dashboard/settings", label: "Settings & team", icon: Building2 }] : navigation;

  return (
    <div className={isInbox ? "flex h-dvh overflow-hidden bg-slate-50 text-slate-900" : "flex min-h-screen bg-slate-50 text-slate-900"}>
      {mobileOpen && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-slate-950/40 lg:hidden" onClick={() => setMobileOpen(false)} />}
      {isInbox ? <aside aria-label="Workspace navigation" className={`z-30 flex h-full shrink-0 flex-col border-r border-slate-800 bg-[#171922] py-3 text-slate-400 shadow-lg transition-[width] duration-200 ${sidebarCollapsed ? "w-[58px]" : "w-64"}`}>
        <div className={`mb-5 flex items-center ${sidebarCollapsed ? "justify-center" : "justify-between px-3"}`}>
          <Link href="/dashboard/inbox" title="SupportPilot Inbox" aria-label="SupportPilot Inbox" className="grid size-10 shrink-0 place-items-center rounded-xl bg-indigo-500 text-lg font-black text-slate-50 shadow-md">S</Link>
          {!sidebarCollapsed && <span className="min-w-0 flex-1 px-3 text-sm font-bold text-slate-50">SupportPilot<span className="mt-0.5 block text-xs font-normal text-slate-400">Support workspace</span></span>}
          <button type="button" onClick={toggleSidebar} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} className="grid size-9 shrink-0 place-items-center rounded-lg text-slate-400 hover:bg-[#222530] hover:text-slate-50">{sidebarCollapsed ? <PanelLeftOpen size={17}/> : <PanelLeftClose size={17}/>}</button>
        </div>
        {!sidebarCollapsed && <div className="mb-4 px-4"><p className="truncate text-xs font-semibold text-slate-200">{user.organization?.name ?? "Your organization"}</p><p className="mt-0.5 truncate text-[11px] text-slate-400">{user.organization?.slug}</p></div>}
        <nav aria-label="Main navigation" className={`flex flex-1 flex-col gap-1.5 ${sidebarCollapsed ? "items-center" : "items-stretch px-3"}`}>
          {links.map(({ href, label, icon: Icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return <Link key={href} href={href} title={sidebarCollapsed ? label : undefined} aria-label={label} aria-current={active ? "page" : undefined} className={`relative rounded-xl transition ${sidebarCollapsed ? "grid size-10 place-items-center" : "flex h-10 w-full items-center gap-3 px-3"} ${active ? "bg-[#292c39] text-slate-50" : "text-slate-400 hover:bg-[#222530] hover:text-slate-50"}`}><Icon size={19}/>{!sidebarCollapsed && <span className="truncate text-sm font-medium">{label}</span>}{active && <span className={`absolute h-5 w-1 rounded-r-full bg-indigo-400 ${sidebarCollapsed ? "-left-3" : "-left-3"}`}/>}</Link>;
          })}
        </nav>
        <button onClick={toggleTheme} title={dark ? "Switch to light theme" : "Switch to dark theme"} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} className="mb-1 grid size-10 place-items-center self-center rounded-xl text-slate-400 hover:bg-[#222530] hover:text-slate-50">{dark ? <Sun size={18}/> : <Moon size={18}/>}</button>
        <button title={`Sign out ${user.email}`} aria-label="Sign out" onClick={() => logout.mutate()} className="grid size-10 place-items-center self-center rounded-xl text-slate-400 hover:bg-[#222530] hover:text-slate-50"><LogOut size={18}/></button>
      </aside> : <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-slate-200 bg-white shadow-xl transition-all duration-200 lg:translate-x-0 lg:shadow-none ${sidebarCollapsed ? "lg:w-[72px]" : "lg:w-64"} ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className={`flex h-20 items-center gap-3 ${sidebarCollapsed ? "justify-center px-3" : "px-6"}`}>
          <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-blue-700 font-black text-white">S</span>
          {!sidebarCollapsed && <span className="min-w-0"><span className="block font-bold tracking-tight">SupportPilot</span><span className="text-xs text-slate-500">Support workspace</span></span>}
          <button className="ml-auto rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={18}/></button>
          <button type="button" onClick={toggleSidebar} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} className="ml-auto hidden size-9 shrink-0 place-items-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 lg:grid">{sidebarCollapsed ? <PanelLeftOpen size={18}/> : <PanelLeftClose size={18}/>}</button>
        </div>
        {!sidebarCollapsed && <div className="mx-4 mb-6 rounded-2xl bg-slate-50 p-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-600"><Building2 size={14}/> Workspace</div>
          <p className="mt-2 truncate text-sm font-semibold text-slate-800">{user.organization?.name ?? "Your organization"}</p>
          <p className="mt-0.5 truncate text-xs text-slate-500">{user.organization?.slug}</p>
        </div>}
        <nav aria-label="Main navigation" className={`space-y-1 ${sidebarCollapsed ? "px-3" : "px-3"}`}>
          {!sidebarCollapsed && <p className="px-3 pb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-600">Workspace</p>}
          {links.map(({ href, label, icon: Icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return <Link key={href} href={href} onClick={() => setMobileOpen(false)} title={sidebarCollapsed ? label : undefined} aria-current={active ? "page" : undefined} className={`flex items-center rounded-xl py-2.5 text-sm font-medium transition ${sidebarCollapsed ? "justify-center px-2" : "gap-3 px-3"} ${active ? "bg-blue-50 text-blue-800" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950"}`}><Icon size={18} className="shrink-0"/>{!sidebarCollapsed && <span className="min-w-0 flex-1 truncate">{label}</span>}{!sidebarCollapsed && active && <span className="size-1.5 shrink-0 rounded-full bg-blue-700"/>}</Link>;
          })}
        </nav>
        <div className="mt-auto border-t border-slate-100 p-4">
          {!sidebarCollapsed && <div className="mb-3 flex items-center gap-2 px-2 text-xs text-slate-600"><CircleHelp size={15}/> Need a hand? <span className="ml-auto text-slate-600">v0.3</span></div>}
          <div className={`flex items-center rounded-xl p-2 ${sidebarCollapsed ? "justify-center" : "gap-3"}`}>
            <div title={sidebarCollapsed ? user.full_name : undefined} className="grid size-9 shrink-0 place-items-center rounded-full bg-blue-100 text-sm font-bold text-blue-800">{user.full_name.slice(0, 1).toUpperCase()}</div>
            {!sidebarCollapsed && <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{user.full_name}</p><p className="truncate text-xs capitalize text-slate-500">{user.role}</p></div>}
            <button title="Sign out" onClick={() => logout.mutate()} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" aria-label="Sign out"><LogOut size={17}/></button>
          </div>
        </div>
      </aside>}
      <div className={isInbox ? "min-w-0 flex-1" : `min-w-0 flex-1 ${sidebarCollapsed ? "lg:pl-[72px]" : "lg:pl-64"}`}>
        {!isInbox && <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-8">
          <div className="flex items-center gap-2"><button aria-label="Open navigation" onClick={() => setMobileOpen(true)} className="rounded-xl p-2 text-slate-600 hover:bg-slate-100 lg:hidden"><Menu size={20}/></button><button type="button" onClick={toggleSidebar} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} className="hidden rounded-xl p-2 text-slate-600 hover:bg-slate-100 lg:inline-flex">{sidebarCollapsed ? <PanelLeftOpen size={20}/> : <PanelLeftClose size={20}/>}</button></div>
          <div role="status" aria-live="polite" className="hidden items-center gap-2 text-sm text-slate-500 sm:flex">
            <Activity size={16} className={readiness.isSuccess ? "text-emerald-500" : readiness.isError ? "text-amber-500" : "animate-pulse text-slate-400"}/>
            {readiness.isSuccess ? "Core services ready" : readiness.isError ? "System status unavailable" : "Checking system status…"}
          </div>
          <div className="ml-3"><CommandSearch/></div>
          <div className="ml-auto flex items-center gap-2 sm:gap-3"><span className="hidden text-sm text-slate-500 md:block">{user.email}</span><button onClick={toggleTheme} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100">{dark ? <Sun size={18}/> : <Moon size={18}/>}</button><Button size="sm" variant="ghost" onClick={() => logout.mutate()}>Sign out</Button></div>
        </header>}
        <main className={isInbox ? "h-dvh w-full overflow-hidden p-0" : "mx-auto w-full max-w-7xl p-4 sm:p-7 lg:p-9"}>{children}</main>
      </div>
    </div>
  );
}
