"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import {
  Building2,
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { getDashboardNavigation, isDashboardNavigationLinkActive } from "@/features/dashboard/navigation/dashboard-navigation";
import type { User } from "@/features/auth/types/user.types";

type AppSidebarProps = {
  user: User;
  collapsed: boolean;
  unreadCount: number;
  hasMoreUnread: boolean;
  mobile?: boolean;
  onToggleCollapse: () => void;
  onOpenSearch: () => void;
  onSwitchWorkspace: () => void;
  onNavigate?: () => void;
};

const GROUPS_STORAGE_KEY = "supportpilot-sidebar-groups";

function subscribeToGroupStorage(notify: () => void) {
  window.addEventListener("storage", notify);
  return () => window.removeEventListener("storage", notify);
}

function readGroupStorage(): string | null {
  try {
    return window.localStorage.getItem(GROUPS_STORAGE_KEY);
  } catch {
    return null;
  }
}

function parseClosedGroups(value: string | null): string[] {
  try {
    const parsed: unknown = value === null ? [] : JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function AppSidebar({
  user,
  collapsed,
  unreadCount,
  hasMoreUnread,
  mobile = false,
  onToggleCollapse,
  onOpenSearch,
  onSwitchWorkspace,
  onNavigate,
}: AppSidebarProps) {
  const pathname = usePathname();
  const groups = getDashboardNavigation(user.role);
  const savedGroups = useSyncExternalStore(subscribeToGroupStorage, readGroupStorage, () => null);
  const [groupOverride, setGroupOverride] = useState<string[]>();
  const closedGroups = groupOverride ?? parseClosedGroups(savedGroups);
  const isCollapsed = collapsed && !mobile;

  function toggleGroup(label: string) {
    const next = closedGroups.includes(label)
      ? closedGroups.filter((item) => item !== label)
      : [...closedGroups, label];
    setGroupOverride(next);
    try {
      window.localStorage.setItem(GROUPS_STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Group preferences still work for the current session.
    }
  }

  const sidebarContents = (
    <div className="flex h-full min-h-0 flex-col bg-background text-foreground">
      <div className={`flex h-[52px] shrink-0 items-center ${isCollapsed ? "justify-center px-2" : "gap-2.5 px-3"}`}>
        <Link href="/dashboard" aria-label="SupportPilot overview" onClick={onNavigate} className="flex min-w-0 items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring/40">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">S</span>
          {!isCollapsed && <span className="min-w-0"><span className="block truncate text-sm font-semibold tracking-tight">SupportPilot</span><span className="block truncate text-[11px] text-muted-foreground">Support workspace</span></span>}
        </Link>
        {mobile ? <Button variant="ghost" size="icon" className="ml-auto" onClick={onNavigate} aria-label="Close navigation"><X/></Button> : isCollapsed ? <Button variant="ghost" size="icon" className="ml-1 hidden lg:inline-flex" onClick={onOpenSearch} aria-label="Search workspace" title="Search workspace"><Search/></Button> : <Button variant="ghost" size="icon-sm" className="ml-auto hidden lg:inline-flex" onClick={onToggleCollapse} aria-label="Collapse sidebar" title="Collapse sidebar"><PanelLeftClose/></Button>}
      </div>

      <div className={`shrink-0 px-2 pb-2 ${isCollapsed ? "pt-1" : "pt-2"}`}>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant={isCollapsed ? "ghost" : "secondary"} className={isCollapsed ? "mx-auto size-9 p-0" : "h-auto min-h-11 w-full justify-start px-2.5 py-2 text-left"} aria-label="Workspace switcher" title={isCollapsed ? user.organization?.name ?? "Workspace" : undefined}/> }>
            <span className="grid size-7 shrink-0 place-items-center rounded-md bg-background text-muted-foreground"><Building2 size={15}/></span>
            {!isCollapsed && <span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold">{user.organization?.name ?? "Workspace"}</span><span className="block truncate text-[10px] font-normal text-muted-foreground">{user.organization?.slug ?? "Current workspace"}</span></span>}
            {!isCollapsed && <ChevronsUpDown size={14} className="shrink-0 text-muted-foreground"/>}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-60">
            <DropdownMenuLabel className="font-normal">
              <span className="block text-xs text-muted-foreground">Current workspace</span>
              <span className="mt-1 block truncate font-semibold text-foreground">{user.organization?.name ?? "Workspace"}</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator/>
            <DropdownMenuItem onClick={onSwitchWorkspace}>Switch workspace</DropdownMenuItem>
            <p className="px-2 py-1 text-[11px] leading-4 text-muted-foreground">You’ll sign in again and choose a workspace.</p>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {!isCollapsed && <div className="shrink-0 px-2 pb-2">
        <Button variant="outline" className="h-9 w-full justify-start gap-2 px-2.5 text-xs font-normal text-muted-foreground" onClick={onOpenSearch} aria-label="Search workspace">
          <Search size={14}/><span className="flex-1 text-left">Search workspace</span><kbd className="rounded border border-border bg-muted px-1 py-0.5 font-mono text-[9px]">⌘K</kbd>
        </Button>
      </div>}

      <TooltipProvider delay={150}>
        <nav aria-label="Main navigation" className={`min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-2 pb-3 ${isCollapsed ? "space-y-2 pt-2" : "space-y-4 pt-1"}`}>
          {groups.map((group) => {
            const activeGroup = group.links.some((link) => isDashboardNavigationLinkActive(pathname, link));
            const groupClosed = closedGroups.includes(group.label) && !activeGroup;
            return <section key={group.label} aria-label={group.label} className="space-y-0.5">
              {!isCollapsed && <button type="button" aria-expanded={!groupClosed} onClick={() => toggleGroup(group.label)} className="flex min-h-7 w-full items-center gap-2 rounded px-2 text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground hover:bg-muted/70">
                <span className="flex-1">{group.label}</span>{groupClosed ? <ChevronRight size={13}/> : <ChevronDown size={13}/>}
              </button>}
              {!groupClosed && group.links.map((link) => {
                const active = isDashboardNavigationLinkActive(pathname, link);
                const route = link.href.split("#", 1)[0];
                const linkNode = <Link key={link.href} href={link.href} onClick={onNavigate} title={isCollapsed ? link.label : undefined} aria-label={isCollapsed ? link.label : undefined} aria-current={active ? "page" : undefined} className={`relative flex min-h-9 items-center gap-2.5 rounded-md px-2 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring/40 ${isCollapsed ? "justify-center px-0" : ""} ${active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>
                  {active && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-primary" aria-hidden="true"/>}
                  <link.icon size={16} strokeWidth={active ? 2.2 : 1.9} className="shrink-0" aria-hidden="true"/>
                  {!isCollapsed && <span className="min-w-0 flex-1 truncate">{link.label}</span>}
                  {!isCollapsed && route === "/dashboard/inbox" && unreadCount > 0 && <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground">{hasMoreUnread ? `${unreadCount}+` : unreadCount}</span>}
                </Link>;
                return isCollapsed ? <Tooltip key={link.href}><TooltipTrigger render={linkNode}/><TooltipContent side="right">{link.label}</TooltipContent></Tooltip> : linkNode;
              })}
            </section>;
          })}
        </nav>
      </TooltipProvider>

      <div className={`shrink-0 border-t border-border p-2 ${isCollapsed ? "flex justify-center" : ""}`}>
        {!mobile && isCollapsed && <Button variant="ghost" size="icon" className="hidden lg:inline-flex" onClick={onToggleCollapse} aria-label="Expand sidebar" title="Expand sidebar"><PanelLeftOpen/></Button>}
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" className={isCollapsed ? "size-9 p-0" : "h-auto w-full justify-start gap-2 px-2 py-2 text-left"} aria-label="User profile menu" title={isCollapsed ? user.full_name : undefined}/> }>
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{user.full_name.slice(0, 1).toUpperCase()}</span>
            {!isCollapsed && <span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold">{user.full_name}</span><span className="block truncate text-[10px] capitalize text-muted-foreground">{user.role}</span></span>}
            {!isCollapsed && <ChevronsUpDown size={13} className="shrink-0 text-muted-foreground"/>}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top" className="w-64">
            <DropdownMenuLabel className="font-normal"><span className="block truncate font-semibold text-foreground">{user.full_name}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{user.email}</span></DropdownMenuLabel>
            <DropdownMenuSeparator/>
            <DropdownMenuItem onClick={onSwitchWorkspace}>Switch workspace</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );

  return <aside className={`flex h-full min-h-0 flex-col border-r border-border bg-background ${isCollapsed ? "w-14" : "w-[248px]"}`}>{sidebarContents}</aside>;
}
