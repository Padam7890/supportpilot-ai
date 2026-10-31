"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, BarChart3, BookOpen, Building2, CircleHelp, Inbox, LogOut, Menu, Moon, Sun, Users, X } from "lucide-react";
import { getCurrentUser, currentUserQueryKey, logout as logoutRequest } from "@/features/auth/api/auth-api";
import { Button } from "@/components/ui/button";

const navigation = [
  { href: "/dashboard", label: "Overview", icon: BarChart3, exact: true },
  { href: "/dashboard/inbox", label: "Inbox", icon: Inbox },
  { href: "/dashboard/knowledge", label: "Knowledge", icon: BookOpen },
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

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [mobileOpen, setMobileOpen] = useState(false);
  const dark = useSyncExternalStore(subscribeTheme, getThemeSnapshot, getThemeServerSnapshot);
  const me = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
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
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {mobileOpen && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-slate-950/40 lg:hidden" onClick={() => setMobileOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-slate-200 bg-white transition-transform lg:translate-x-0 ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex h-20 items-center gap-3 px-6">
          <span className="flex size-10 items-center justify-center rounded-2xl bg-blue-700 font-black text-white">S</span>
          <span><span className="block font-bold tracking-tight">SupportPilot</span><span className="text-xs text-slate-500">Support workspace</span></span>
          <button className="ml-auto rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={18}/></button>
        </div>
        <div className="mx-4 mb-6 rounded-2xl bg-slate-50 p-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400"><Building2 size={14}/> Workspace</div>
          <p className="mt-2 truncate text-sm font-semibold text-slate-800">{user.organization?.name ?? "Your organization"}</p>
          <p className="mt-0.5 truncate text-xs text-slate-500">{user.organization?.slug}</p>
        </div>
        <nav aria-label="Main navigation" className="space-y-1 px-3">
          <p className="px-3 pb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-400">Workspace</p>
          {links.map(({ href, label, icon: Icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return <Link key={href} href={href} onClick={() => setMobileOpen(false)} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${active ? "bg-blue-50 text-blue-800" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950"}`}><Icon size={18}/>{label}{active && <span className="ml-auto size-1.5 rounded-full bg-blue-700"/>}</Link>;
          })}
        </nav>
        <div className="mt-auto border-t border-slate-100 p-4">
          <div className="mb-3 flex items-center gap-2 px-2 text-xs text-slate-500"><CircleHelp size={15}/> Need a hand? <span className="ml-auto text-slate-400">v0.3</span></div>
          <div className="flex items-center gap-3 rounded-xl p-2">
            <div className="grid size-9 shrink-0 place-items-center rounded-full bg-blue-100 text-sm font-bold text-blue-800">{user.full_name.slice(0, 1).toUpperCase()}</div>
            <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{user.full_name}</p><p className="truncate text-xs capitalize text-slate-500">{user.role}</p></div>
            <button title="Sign out" onClick={() => logout.mutate()} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" aria-label="Sign out"><LogOut size={17}/></button>
          </div>
        </div>
      </aside>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-8">
          <button aria-label="Open navigation" onClick={() => setMobileOpen(true)} className="rounded-xl p-2 text-slate-600 hover:bg-slate-100 lg:hidden"><Menu size={20}/></button>
          <div className="hidden items-center gap-2 text-sm text-slate-500 sm:flex"><Activity size={16} className="text-emerald-500"/> All systems operational</div>
          <div className="ml-auto flex items-center gap-2 sm:gap-3"><span className="hidden text-sm text-slate-500 md:block">{user.email}</span><button onClick={toggleTheme} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100">{dark ? <Sun size={18}/> : <Moon size={18}/>}</button><Button size="sm" variant="ghost" onClick={() => logout.mutate()}>Sign out</Button></div>
        </header>
        <main className="mx-auto max-w-7xl p-4 sm:p-7 lg:p-9">{children}</main>
      </div>
    </div>
  );
}
