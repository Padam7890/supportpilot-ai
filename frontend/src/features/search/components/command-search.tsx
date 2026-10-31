"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, LoaderCircle, Search, Ticket, Users, X } from "lucide-react";
import { searchWorkspace } from "../api/search-api";

const icons = { ticket: Ticket, customer: Users, document: FileText } as const;

export function CommandSearch() {
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const results = useQuery({
    queryKey: ["workspace-search", query],
    queryFn: () => searchWorkspace(query.trim()),
    enabled: open && query.trim().length >= 2,
    staleTime: 5_000,
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      } else if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (open) return;
    trigger.current?.focus();
  }, [open]);

  return <>
    <button ref={trigger} type="button" onClick={() => setOpen(true)} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-500 hover:border-slate-300 hover:text-slate-800" aria-label="Search workspace ⌘ K"><Search size={15}/><span className="hidden md:inline">Search workspace</span><kbd aria-hidden="true" className="hidden rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] md:inline">⌘ K</kbd></button>
    {open && <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/40 px-4 pt-[12vh]" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <section ref={dialog} role="dialog" aria-modal="true" aria-labelledby="workspace-search-title" onKeyDown={(event) => { if (event.key !== "Tab") return; const focusable = dialog.current?.querySelectorAll<HTMLElement>('input:not([disabled]), button:not([disabled]), a[href]'); if (!focusable?.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } }} className="w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
        <h2 id="workspace-search-title" className="sr-only">Search workspace</h2>
        <div className="flex items-center gap-3 border-b border-slate-100 px-4"><Search size={19} className="shrink-0 text-slate-400"/><input autoFocus aria-label="Search tickets, customers, or documents" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tickets, customers, or documents…" className="h-14 min-w-0 flex-1 bg-transparent text-sm outline-none"/><button type="button" onClick={() => setOpen(false)} aria-label="Close search" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><X size={17}/></button></div>
        <div className="max-h-[60vh] overflow-y-auto p-2" aria-live="polite">
          {query.trim().length < 2 && <p className="px-3 py-8 text-center text-sm text-slate-500">Enter at least two characters to search your workspace.</p>}
          {query.trim().length >= 2 && results.isPending && <p role="status" className="flex items-center justify-center gap-2 px-3 py-8 text-sm text-slate-500"><LoaderCircle size={16} className="animate-spin"/>Searching…</p>}
          {results.isError && <p role="alert" className="px-3 py-8 text-center text-sm text-red-700">Workspace search is unavailable. Try again.</p>}
          {results.data?.items.length === 0 && <p className="px-3 py-8 text-center text-sm text-slate-500">No tickets, customers, or documents matched.</p>}
          {results.data?.items.map((item) => { const Icon = icons[item.kind]; return <Link key={`${item.kind}:${item.id}`} href={item.href} onClick={() => setOpen(false)} className="flex items-center gap-3 rounded-xl px-3 py-3 hover:bg-blue-50 focus:bg-blue-50 focus:outline-none"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600"><Icon size={17}/></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-slate-900">{item.title}</span><span className="mt-0.5 block truncate text-xs text-slate-500">{item.subtitle}</span></span><span className="shrink-0 rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold capitalize text-slate-600">{item.kind}</span></Link>; })}
        </div>
        <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-[11px] text-slate-400"><span>Search is limited to your workspace access.</span><span>Esc to close</span></div>
      </section>
    </div>}
  </>;
}
