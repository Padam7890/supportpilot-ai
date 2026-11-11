"use client";

import Link from "next/link";
import { useMemo } from "react";
import { Activity, BookOpen, ChevronRight, CircleHelp, LogOut, Moon, Search, Sun, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MobileNavigation } from "@/components/mobile-navigation";
import { CommandSearch } from "@/features/search/components/command-search";
import { getDashboardNavigation } from "@/features/dashboard/navigation/dashboard-navigation";
import type { User } from "@/features/auth/types/user.types";
import { NotificationPopover } from "@/features/notifications/components/notification-popover";

type DashboardTopbarProps = {
  pathname: string;
  user: User;
  serviceState: "ready" | "unavailable" | "checking";
  workerState: "online" | "offline" | "unavailable" | "checking";
  workerCount?: number;
  dark: boolean;
  mobileOpen: boolean;
  searchOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
  onSearchOpenChange: (open: boolean) => void;
  onToggleTheme: () => void;
  onSignOut: () => void;
  unreadCount: number;
  hasMoreUnread: boolean;
};

function breadcrumbs(pathname: string, role: string) {
  const links = getDashboardNavigation(role).flatMap((group) => group.links);
  const current = links.find((link) => link.href === pathname) ?? links.find((link) => {
    const route = link.href.split("#", 1)[0];
    return pathname === route || pathname.startsWith(`${route}/`);
  });
  if (!current || pathname === "/dashboard") return [{ label: "Workspace", href: "/dashboard" }, { label: "Overview" }];
  const path = current.href.split("#", 1)[0];
  const parent = links.find((link) => link.href === current.parentHref);
  const items = [
    { label: "Workspace", href: "/dashboard" },
    ...(parent ? [{ label: parent.label, href: parent.href }] : []),
    { label: current.label, href: path },
  ];
  if (pathname !== path) items.push({ label: "Details", href: "" });
  return items;
}

export function DashboardTopbar(props: DashboardTopbarProps) {
  const crumbItems = useMemo(() => breadcrumbs(props.pathname, props.user.role), [props.pathname, props.user.role]);

  return <header className="sticky top-0 z-20 flex h-[52px] items-center gap-2 border-b border-border bg-background/95 px-2.5 backdrop-blur sm:px-4">
    <MobileNavigation open={props.mobileOpen} onOpenChange={props.onMobileOpenChange} user={props.user} unreadCount={props.unreadCount} hasMoreUnread={props.hasMoreUnread} onOpenSearch={() => props.onSearchOpenChange(true)} onSwitchWorkspace={props.onSignOut}/>
    <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1 text-xs sm:flex">
      <span className="truncate text-muted-foreground">{crumbItems[0]?.label}</span>
      {crumbItems.slice(1).map((item, index) => <span className="flex min-w-0 items-center gap-1" key={`${item.label}-${index}`}>
        <ChevronRight size={13} className="shrink-0 text-muted-foreground/60" aria-hidden="true"/>
        {item.href ? <span className={index === crumbItems.length - 2 ? "truncate font-medium text-foreground" : "truncate text-muted-foreground"}>{item.label}</span> : <span className="truncate font-medium text-foreground">{item.label}</span>}
      </span>)}
    </nav>

    <div className="hidden min-w-0 flex-1 items-center gap-3 lg:flex">
      <span role="status" aria-live="polite" className="flex shrink-0 items-center gap-1.5 text-[11px] text-muted-foreground">
        <Activity size={14} className={props.serviceState === "ready" ? "text-emerald-600" : props.serviceState === "unavailable" ? "text-amber-600" : "animate-pulse"}/>
        {props.serviceState === "ready" ? "Services ready" : props.serviceState === "unavailable" ? "Services unavailable" : "Checking services"}
      </span>
      <span className={`shrink-0 border-l border-border pl-3 text-[11px] ${props.workerState === "online" ? "text-emerald-700" : props.workerState === "offline" ? "text-amber-700" : "text-muted-foreground"}`} title={props.workerCount === undefined ? undefined : `${props.workerCount} active workers`}>
        {props.workerState === "online" ? "Worker online" : props.workerState === "offline" ? "Worker offline" : props.workerState === "checking" ? "Checking worker" : "Worker status unavailable"}
      </span>
    </div>

    <div className="ml-auto flex min-w-0 items-center gap-1.5">
      <CommandSearch open={props.searchOpen} onOpenChange={props.onSearchOpenChange}/>
      <NotificationPopover />

      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label="Help menu"/>}><CircleHelp size={16}/></DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuLabel>Help & workspace</DropdownMenuLabel>
          <DropdownMenuItem render={<Link href="/dashboard/knowledge"/>}><BookOpen size={14}/>Knowledge library</DropdownMenuItem>
          <DropdownMenuItem render={<Link href="/dashboard/widget"/>}><Search size={14}/>Widget setup</DropdownMenuItem>
          <DropdownMenuItem render={<Link href="/dashboard/inbox"/>}>Open inbox</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Button variant="ghost" size="icon" onClick={props.onToggleTheme} aria-label={props.dark ? "Switch to light theme" : "Switch to dark theme"} title={props.dark ? "Light theme" : "Dark theme"}>{props.dark ? <Sun size={16}/> : <Moon size={16}/>}</Button>

      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" className="h-9 gap-2 px-1.5 sm:px-2" aria-label="User profile menu"/>}>
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">{props.user.full_name.slice(0, 1).toUpperCase()}</span>
          <span className="hidden max-w-32 truncate text-xs font-medium sm:inline">{props.user.full_name}</span>
          <UserRound size={14} className="hidden text-muted-foreground sm:inline"/>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuLabel className="font-normal"><span className="block truncate font-semibold text-foreground">{props.user.full_name}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{props.user.email}</span><span className="mt-1 block truncate text-[10px] capitalize text-muted-foreground">{props.user.organization?.name} · {props.user.role}</span></DropdownMenuLabel>
          <DropdownMenuSeparator/>
          <DropdownMenuItem onClick={props.onSignOut}>Switch workspace</DropdownMenuItem>
          <DropdownMenuItem onClick={props.onSignOut}><LogOut size={14}/>Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  </header>;
}
