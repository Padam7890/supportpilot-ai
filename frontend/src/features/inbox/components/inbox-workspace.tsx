"use client";

import { useEffect, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Search, Send, UserRound } from "lucide-react";
import { MotionConfig, motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/input";
import { listConversations, listMessages, sendMessage } from "@/features/conversations/api/conversation-api";
import { sendMessageSchema } from "@/features/conversations/schemas/conversation.schema";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { getInbox, inboxQueryKeys, markConversationRead } from "../api/inbox-api";
import type { InboxFilters } from "../api/inbox-api";
import type { InboxItem } from "../types/inbox.types";
import { formatDateTime } from "@/lib/utils";

const initialFilters: InboxFilters = { scope: "all", status: "", priority: "", search: "" };

export function InboxWorkspace() {
  const client = useQueryClient();
  const [filters, setFilters] = useState(initialFilters);
  const [searchDraft, setSearchDraft] = useState("");
  const [selectedTicket, setSelectedTicket] = useState<InboxItem | null>(null);
  const [selectedConversation, setSelectedConversation] = useState("");
  const [reply, setReply] = useState("");
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const inbox = useInfiniteQuery({
    queryKey: inboxQueryKeys.page(filters),
    queryFn: ({ pageParam }) => getInbox(filters, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 20_000 : false,
    refetchIntervalInBackground: false,
  });
  const rows = inbox.data?.pages.flatMap((page) => page.items) ?? [];
  const conversations = useQuery({
    queryKey: inboxQueryKeys.conversations(selectedTicket?.ticketId),
    queryFn: () => listConversations(selectedTicket!.ticketId),
    enabled: Boolean(selectedTicket),
  });
  const messages = useQuery({
    queryKey: inboxQueryKeys.messages(selectedConversation || undefined),
    queryFn: () => listMessages(selectedConversation),
    enabled: Boolean(selectedConversation),
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 10_000 : false,
    refetchIntervalInBackground: false,
  });
  const read = useMutation({ mutationFn: markConversationRead, onSuccess: async () => {
    await client.invalidateQueries({ queryKey: ["inbox"] });
  } });
  const send = useMutation({ mutationFn: () => sendMessage(selectedConversation, sendMessageSchema.parse({ content: reply })), onSuccess: async () => {
    setReply("");
    await Promise.all([client.invalidateQueries({ queryKey: inboxQueryKeys.messages(selectedConversation) }), client.invalidateQueries({ queryKey: ["inbox"] })]);
  } });

  useEffect(() => {
    if (conversations.data?.length === 1 && !selectedConversation) chooseConversation(conversations.data[0].id);
    // A multi-thread ticket must stay unselected until the user chooses.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversations.data]);

  function chooseConversation(id: string) {
    setSelectedConversation(id);
    read.mutate(id);
  }
  function selectTicket(item: InboxItem) {
    setSelectedTicket(item);
    setSelectedConversation("");
  }

  const canReply = ["owner", "admin", "agent"].includes(me.data?.role ?? "");

  return <MotionConfig reducedMotion="user"><div className="-mx-4 -my-4 sm:-mx-7 sm:-my-7 lg:-mx-9 lg:-my-9">
    <div className="flex min-h-[calc(100dvh-4rem)] flex-col bg-white lg:flex-row">
      <section aria-label="Inbox tickets" className={`${selectedTicket ? "hidden lg:flex" : "flex"} w-full flex-col border-r border-slate-200 lg:w-[320px] xl:w-[350px]`}>
        <header className="space-y-4 border-b border-slate-200 p-5">
          <div className="flex items-start justify-between"><div><p className="text-xs font-bold uppercase tracking-[.16em] text-blue-700">Support workspace</p><h1 className="mt-1 text-2xl font-bold">Inbox</h1></div><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">{rows.length}{inbox.hasNextPage ? "+" : ""} tickets</span></div>
          <label className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5"><Search size={16} className="text-slate-400"/><span className="sr-only">Search inbox</span><input className="min-w-0 flex-1 bg-transparent text-sm outline-none" placeholder="Search tickets or customers" value={searchDraft} onChange={(e) => setSearchDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") setFilters((value) => ({ ...value, search: searchDraft })); }}/><button className="text-xs font-semibold text-blue-700" onClick={() => setFilters((value) => ({ ...value, search: searchDraft }))}>Search</button></label>
          <div className="grid grid-cols-3 gap-2"><FilterButton active={filters.scope === "all"} onClick={() => setFilters({ ...filters, scope: "all" })}>All</FilterButton><FilterButton active={filters.scope === "mine"} onClick={() => setFilters({ ...filters, scope: "mine" })}>Mine</FilterButton><FilterButton active={filters.scope === "unassigned"} onClick={() => setFilters({ ...filters, scope: "unassigned" })}>Unassigned</FilterButton></div>
          <div className="grid grid-cols-2 gap-2"><Select aria-label="Filter by status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All statuses</option>{["open", "pending", "resolved", "closed"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</Select><Select aria-label="Filter by priority" value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value })}><option value="">All priorities</option>{["low", "normal", "high", "urgent"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</Select></div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">
          {inbox.isPending && <div className="space-y-3 p-4">{[1,2,3,4].map((i) => <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100"/>)}</div>}
          {inbox.isError && <div role="alert" className="m-4 rounded-xl bg-red-50 p-4 text-sm text-red-700">Could not load the inbox. <button className="font-semibold underline" onClick={() => inbox.refetch()}>Try again</button></div>}
          {!inbox.isPending && !inbox.isError && rows.length === 0 && <div className="p-8 text-center"><p className="font-semibold">No tickets match</p><p className="mt-1 text-sm text-slate-500">Change a filter or clear your search.</p></div>}
          {rows.map((item) => <button key={item.ticketId} onClick={() => selectTicket(item)} aria-pressed={selectedTicket?.ticketId === item.ticketId} className={`w-full border-b border-slate-100 p-4 text-left transition hover:bg-slate-50 ${selectedTicket?.ticketId === item.ticketId ? "bg-blue-50/70" : ""}`}><div className="flex items-start gap-3"><Avatar name={item.customer.name}/><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><p className="truncate text-sm font-semibold">{item.customer.name}</p><time className="shrink-0 text-[11px] text-slate-400">{relative(item.updatedAt)}</time></div><p className="mt-1 truncate text-sm font-medium text-slate-800">{item.subject}</p><p className="mt-1 truncate text-xs text-slate-500">{item.latestMessage?.preview ?? "No messages yet"}</p><div className="mt-2 flex items-center gap-2"><StatusPill value={item.status}/><span className="text-[11px] capitalize text-slate-500">{item.priority}</span>{item.unreadCount > 0 && <span className="ml-auto rounded-full bg-blue-700 px-2 py-0.5 text-[10px] font-bold text-white">{item.unreadCount} new</span>}</div></div></div></button>)}
          {inbox.hasNextPage && <div className="p-4"><Button variant="secondary" className="w-full" disabled={inbox.isFetchingNextPage} onClick={() => inbox.fetchNextPage()}>{inbox.isFetchingNextPage ? "Loading…" : "Load more"}</Button></div>}
        </div>
      </section>

      <section aria-label="Conversation thread" className={`${selectedTicket ? "flex" : "hidden lg:flex"} min-w-0 flex-1 flex-col`}>
        {!selectedTicket ? <EmptyThread/> : <>
          <header className="flex min-h-[76px] items-center gap-3 border-b border-slate-200 px-4 py-3 sm:px-6"><button className="rounded-lg p-2 hover:bg-slate-100 lg:hidden" aria-label="Back to inbox" onClick={() => setSelectedTicket(null)}><ArrowLeft size={18}/></button><Avatar name={selectedTicket.customer.name}/><div className="min-w-0 flex-1"><p className="truncate font-semibold">{selectedTicket.customer.name}</p><p className="truncate text-xs text-slate-500">{selectedTicket.subject}</p></div><StatusPill value={selectedTicket.status}/></header>
          <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50/60 p-4 sm:p-6" aria-live="polite">
            {conversations.isPending && <p className="text-sm text-slate-500">Loading conversations…</p>}
            {conversations.isError && <p role="alert" className="text-sm text-red-700">Could not load conversations for this ticket.</p>}
            {read.isError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">Could not update this conversation’s read status.</p>}
            {conversations.data && conversations.data.length > 1 && !selectedConversation && <div className="mx-auto max-w-xl rounded-2xl border border-blue-200 bg-white p-6 shadow-sm"><p className="font-semibold">Choose a conversation</p><p className="mt-1 text-sm text-slate-500">This ticket has separate conversation histories. Select one to view its messages.</p><div className="mt-4 space-y-2">{conversations.data.map((conversation, index) => <button key={conversation.id} onClick={() => chooseConversation(conversation.id)} className="flex w-full items-center justify-between rounded-xl border border-slate-200 p-3 text-left hover:border-blue-300 hover:bg-blue-50"><span><span className="block text-sm font-semibold">Conversation {conversations.data!.length - index}</span><span className="text-xs text-slate-500">{titleCase(conversation.channel)} · updated {formatDateTime(conversation.updated_at)}</span></span><span aria-hidden className="text-blue-700">→</span></button>)}</div></div>}
            {selectedConversation && messages.isPending && <div className="h-32 animate-pulse rounded-2xl bg-slate-200"/>}
            {selectedConversation && messages.isError && <p role="alert" className="text-sm text-red-700">Could not load this conversation.</p>}
            {messages.data?.map((message) => { const fromAgent = message.sender_type === "agent"; return <motion.div key={message.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }} className={`flex ${fromAgent ? "justify-end" : "justify-start"}`}><article className={`max-w-[88%] rounded-2xl px-4 py-3 sm:max-w-[72%] ${fromAgent ? "rounded-br-md bg-blue-700 text-white" : "rounded-bl-md border border-slate-200 bg-white"}`}><div className={`mb-1.5 flex gap-2 text-xs ${fromAgent ? "text-blue-100" : "text-slate-500"}`}><span className="font-semibold">{message.sender_name ?? titleCase(message.sender_type)}</span><time>{formatDateTime(message.created_at)}</time></div><p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p></article></motion.div>; })}
            {selectedConversation && messages.data?.length === 0 && <p className="py-10 text-center text-sm text-slate-500">No messages in this conversation.</p>}
          </div>
          {selectedConversation && <form onSubmit={(event) => { event.preventDefault(); if (reply.trim()) send.mutate(); }} className="border-t border-slate-200 bg-white p-4 sm:p-5"><Textarea aria-label="Write a reply" placeholder={canReply ? "Reply to the customer…" : "Your role has read-only access"} value={reply} disabled={!canReply || send.isPending} onChange={(event) => setReply(event.target.value)} className="min-h-24"/><div className="mt-3 flex items-center justify-between"><span className="text-xs text-slate-400">Messages are sent as you.</span><Button type="submit" disabled={!canReply || !reply.trim() || send.isPending}>{send.isPending ? "Sending…" : "Send reply"}<Send size={15}/></Button></div>{send.isError && <p role="alert" className="mt-2 text-sm text-red-700">{send.error instanceof Error ? send.error.message : "Message could not be sent."}</p>}</form>}
        </>}
      </section>

      {selectedTicket && <aside aria-label="Customer context" className="hidden w-[290px] shrink-0 border-l border-slate-200 bg-white xl:block"><div className="border-b border-slate-200 px-5 py-5"><div className="flex items-center gap-3"><Avatar name={selectedTicket.customer.name}/><div className="min-w-0"><p className="truncate font-semibold">{selectedTicket.customer.name}</p><p className="truncate text-xs text-slate-500">{selectedTicket.customer.email ?? "No email"}</p></div></div></div><div className="space-y-5 p-5"><Context label="Ticket" value={selectedTicket.subject}/><Context label="Status" value={titleCase(selectedTicket.status)}/><Context label="Priority" value={titleCase(selectedTicket.priority)}/><Context label="Assignee" value={selectedTicket.assignee?.name ?? "Unassigned"}/><Context label="Last activity" value={formatDateTime(selectedTicket.updatedAt)}/><a href={`/dashboard/customers/${selectedTicket.customer.id}`} className="flex items-center gap-2 text-sm font-semibold text-blue-700 hover:underline"><UserRound size={16}/> View customer profile</a></div></aside>}
    </div>
  </div></MotionConfig>;
}

function FilterButton({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) { return <button onClick={onClick} className={`rounded-lg px-2 py-2 text-xs font-semibold ${active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>{children}</button>; }
function Avatar({ name }: { name: string }) { return <span className="grid size-10 shrink-0 place-items-center rounded-full bg-violet-100 text-sm font-bold text-violet-800">{name.trim().slice(0, 1).toUpperCase()}</span>; }
function StatusPill({ value }: { value: string }) { const colors: Record<string, string> = { open: "bg-emerald-50 text-emerald-700", pending: "bg-amber-50 text-amber-700", resolved: "bg-blue-50 text-blue-700", closed: "bg-slate-100 text-slate-600" }; return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${colors[value] ?? colors.closed}`}>{value}</span>; }
function Context({ label, value }: { label: string; value: string }) { return <div><p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">{label}</p><p className="mt-1 text-sm font-medium text-slate-800">{value}</p></div>; }
function EmptyThread() { return <div className="grid flex-1 place-items-center p-8 text-center"><div><span className="mx-auto grid size-14 place-items-center rounded-2xl bg-blue-50 text-blue-700"><Send size={22}/></span><h2 className="mt-4 text-lg font-semibold">Select a ticket</h2><p className="mt-1 max-w-xs text-sm text-slate-500">Choose a conversation from your inbox to read and reply.</p></div></div>; }
function titleCase(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function relative(value: string) { const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60_000)); if (minutes < 1) return "now"; if (minutes < 60) return `${minutes}m`; const hours = Math.floor(minutes / 60); if (hours < 24) return `${hours}h`; return `${Math.floor(hours / 24)}d`; }
