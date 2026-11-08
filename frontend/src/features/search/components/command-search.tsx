"use client";

import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { FileText, LoaderCircle, Search, Ticket, Users, X } from "lucide-react";
import { Button, Dialog, DialogContent, Input } from "@/components/ui";
import { getCurrentUser, currentUserQueryKey } from "@/features/auth/api/auth-api";
import { getDashboardNavigation } from "@/features/dashboard/navigation/dashboard-navigation";
import { searchWorkspace } from "../api/search-api";

const RECENT_DESTINATIONS_KEY = "supportpilot-recent-destinations";
function getResultIcon(kind: string) {
  if (kind === "ticket") return Ticket;
  if (kind === "customer") return Users;
  if (kind === "document") return FileText;
  return Search;
}

type CommandItem = {
  id: string;
  title: string;
  subtitle: string;
  href: string;
  kind: string;
  icon: typeof Search;
};

type CommandSearchProps = {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

export function CommandSearch({ open: controlledOpen, onOpenChange }: CommandSearchProps = {}) {
  const router = useRouter();
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const setOpen = (next: boolean) => {
    setLocalOpen(next);
    onOpenChange?.(next);
  };
  const [query, setQuery] = useState("");
  const [recentHrefs, setRecentHrefs] = useState<string[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const me = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const search = useQuery({
    queryKey: ["workspace-search", query],
    queryFn: () => searchWorkspace(query.trim()),
    enabled: open && query.trim().length >= 2,
    staleTime: 5_000,
  });

  const routes = useMemo<CommandItem[]>(() => getDashboardNavigation(me.data?.role ?? "viewer")
    .flatMap((group) => group.links)
    .map((link) => ({
      id: `route:${link.href}`,
      title: link.label,
      subtitle: link.href,
      href: link.href,
      kind: "page",
      icon: link.icon,
    })), [me.data?.role]);

  const backendItems = useMemo<CommandItem[]>(() => (search.data?.items ?? []).map((item) => ({
    id: `${item.kind}:${item.id}`,
    title: item.title,
    subtitle: item.subtitle,
    href: item.href,
    kind: item.kind,
    icon: getResultIcon(item.kind),
  })), [search.data?.items]);
  const visibleRoutes = routes.filter((item) => !query.trim() || `${item.title} ${item.subtitle}`.toLowerCase().includes(query.trim().toLowerCase()));
  const items = useMemo(() => {
    if (query.trim()) {
      const known = new Set(visibleRoutes.map((item) => item.href));
      return [...visibleRoutes, ...backendItems.filter((item) => !known.has(item.href))];
    }
    const recent = recentHrefs.map((href) => routes.find((item) => item.href === href)).filter((item): item is CommandItem => Boolean(item));
    const recentSet = new Set(recent.map((item) => item.href));
    return [...recent, ...routes.filter((item) => !recentSet.has(item.href)).slice(0, 6)];
  }, [backendItems, query, recentHrefs, routes, visibleRoutes]);

  useEffect(() => {
    if (!open) return;
    try {
      const saved = window.localStorage.getItem(RECENT_DESTINATIONS_KEY);
      setRecentHrefs(saved ? JSON.parse(saved) as string[] : []);
    } catch {
      setRecentHrefs([]);
    }
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query, items.length]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function navigateTo(item: CommandItem) {
    const nextRecents = [item.href, ...recentHrefs.filter((href) => href !== item.href)].slice(0, 5);
    setRecentHrefs(nextRecents);
    window.localStorage.setItem(RECENT_DESTINATIONS_KEY, JSON.stringify(nextRecents));
    setOpen(false);
    setQuery("");
    router.push(item.href);
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" && items.length) {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % items.length);
    } else if (event.key === "ArrowUp" && items.length) {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + items.length) % items.length);
    } else if (event.key === "Enter" && items[activeIndex]) {
      event.preventDefault();
      navigateTo(items[activeIndex]);
    }
  }

  return <>
    <Button variant="outline" className="h-9 w-full max-w-56 justify-start gap-2 px-2.5 text-xs font-normal text-muted-foreground sm:w-auto sm:min-w-52" type="button" onClick={() => setOpen(true)} aria-label="Search workspace, Command K">
      <Search size={15}/><span className="hidden flex-1 text-left sm:inline">Search workspace</span><kbd className="ml-auto rounded border border-border bg-muted px-1 py-0.5 font-mono text-[9px]">⌘K</kbd>
    </Button>
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (!next) setQuery(""); }}>
      <DialogContent showCloseButton={false} aria-label="Workspace command menu" className="top-[12vh] w-[min(640px,calc(100vw-1.5rem))] max-w-none translate-y-0 gap-0 overflow-hidden rounded-xl p-0 sm:max-w-none">
        <div className="flex items-center gap-3 border-b border-border px-3">
          <Search size={17} className="shrink-0 text-muted-foreground" aria-hidden="true"/>
          <Input autoFocus aria-label="Search pages, tickets, customers, and documents" aria-controls="command-menu-results" aria-activedescendant={items[activeIndex] ? `command-item-${activeIndex}` : undefined} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={handleInputKeyDown} placeholder="Search pages, tickets, customers…" className="h-12 min-w-0 flex-1 border-0 bg-transparent px-0 shadow-none focus-visible:border-transparent focus-visible:ring-0"/>
          <Button variant="ghost" size="icon-sm" onClick={() => setOpen(false)} aria-label="Close search"><X/></Button>
        </div>
        <div id="command-menu-results" role="listbox" aria-label={query ? "Search results" : "Recent destinations and pages"} className="max-h-[min(60vh,480px)] overflow-y-auto p-2">
          {search.isPending && query.trim().length >= 2 && <p role="status" className="flex items-center justify-center gap-2 px-3 py-6 text-sm text-muted-foreground"><LoaderCircle size={15} className="animate-spin"/>Searching workspace…</p>}
          {search.isError && <p role="alert" className="px-3 py-6 text-center text-sm text-destructive">Workspace records could not be searched. You can still open the pages listed below.</p>}
          {!search.isPending && !items.length && <p className="px-3 py-8 text-center text-sm text-muted-foreground">No matching pages or workspace records.</p>}
          {items.map((item, index) => { const Icon = item.icon; return <button id={`command-item-${index}`} key={item.id} type="button" role="option" aria-selected={index === activeIndex} onMouseMove={() => setActiveIndex(index)} onClick={() => navigateTo(item)} className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors ${index === activeIndex ? "bg-accent text-accent-foreground" : "text-foreground hover:bg-muted"}`}>
            <span className="grid size-8 shrink-0 place-items-center rounded-md bg-background text-muted-foreground"><Icon size={16}/></span>
            <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{item.title}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{item.subtitle}</span></span>
            <span className="shrink-0 text-[10px] capitalize text-muted-foreground">{item.kind}</span>
          </button>; })}
        </div>
        <div className="flex items-center justify-between border-t border-border px-3 py-2 text-[10px] text-muted-foreground"><span>Search is limited to pages and records available to your role.</span><span>↑↓ · Enter · Esc</span></div>
      </DialogContent>
    </Dialog>
  </>;
}
