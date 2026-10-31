"use client";

import { useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, LoaderCircle, PanelRight, Search, Send, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/input";
import { listConversations, listInternalNotes, listMessages, sendInternalNote, sendMessage } from "@/features/conversations/api/conversation-api";
import { sendMessageSchema } from "@/features/conversations/schemas/conversation.schema";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { getInbox, inboxQueryKeys, markConversationRead } from "../api/inbox-api";
import type { InboxFilters } from "../api/inbox-api";
import type { InboxItem } from "../types/inbox.types";
import { formatDateTime } from "@/lib/utils";
import { CustomerContextPanel } from "./customer-context-panel";
import { aiQueryKeys, createReplyDraft, getAIExecution, getWidgetAIReplyStatus } from "@/features/ai/api/ai-api";

const initialFilters: InboxFilters = { scope: "all", status: "", priority: "", search: "" };

export function InboxWorkspace() {
  const client = useQueryClient();
  const [filters, setFilters] = useState(initialFilters);
  const [searchDraft, setSearchDraft] = useState("");
  const [selectedTicket, setSelectedTicket] = useState<InboxItem | null>(null);
  const [selectedConversation, setSelectedConversation] = useState("");
  const [showDetails, setShowDetails] = useState(false);
  const [reply, setReply] = useState("");
  const [shopifyOrderNumber, setShopifyOrderNumber] = useState("");
  const [composeMode, setComposeMode] = useState<"reply" | "note">("reply");
  const [draftExecutionId, setDraftExecutionId] = useState<string>();
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const inbox = useInfiniteQuery({
    queryKey: inboxQueryKeys.page(filters),
    queryFn: ({ pageParam }) => getInbox(filters, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 20_000 : false,
    refetchIntervalInBackground: false,
  });
  const rows = useMemo(() => inbox.data?.pages.flatMap((page) => page.items) ?? [], [inbox.data]);
  const activeTicket = selectedTicket ? rows.find((item) => item.ticketId === selectedTicket.ticketId) ?? selectedTicket : null;
  const conversations = useQuery({
    queryKey: inboxQueryKeys.conversations(activeTicket?.ticketId),
    queryFn: () => listConversations(activeTicket!.ticketId),
    enabled: Boolean(activeTicket),
  });
  const messages = useQuery({
    queryKey: inboxQueryKeys.messages(selectedConversation || undefined),
    queryFn: () => listMessages(selectedConversation),
    enabled: Boolean(selectedConversation),
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 10_000 : false,
    refetchIntervalInBackground: false,
  });
  const notes = useQuery({
    queryKey: ["internal-notes", selectedConversation || undefined],
    queryFn: () => listInternalNotes(selectedConversation),
    enabled: Boolean(selectedConversation),
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 10_000 : false,
    refetchIntervalInBackground: false,
  });
  const isWidgetConversation = conversations.data?.some((item) => item.id === selectedConversation && item.channel === "shopify_widget") ?? false;
  const widgetAI = useQuery({
    queryKey: ["widget-ai-reply", selectedConversation],
    queryFn: () => getWidgetAIReplyStatus(selectedConversation),
    enabled: Boolean(selectedConversation && isWidgetConversation),
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 4000 : false,
    refetchIntervalInBackground: false,
  });
  const read = useMutation({ mutationFn: markConversationRead, onSuccess: async () => {
    await client.invalidateQueries({ queryKey: ["inbox"] });
  } });
  const send = useMutation({ mutationFn: () => composeMode === "note"
    ? sendInternalNote(selectedConversation, sendMessageSchema.parse({ content: reply }).content)
    : sendMessage(selectedConversation, sendMessageSchema.parse({ content: reply })), onSuccess: async () => {
    setReply("");
    setDraftExecutionId(undefined);
    await Promise.all([client.invalidateQueries({ queryKey: inboxQueryKeys.messages(selectedConversation) }), client.invalidateQueries({ queryKey: ["internal-notes", selectedConversation] }), client.invalidateQueries({ queryKey: ["inbox"] }), client.invalidateQueries({ queryKey: ["widget-ai-reply", selectedConversation] })]);
  } });
  const createDraft = useMutation({
    mutationFn: () => createReplyDraft({ conversation_id: selectedConversation, ...(shopifyOrderNumber.trim() ? { shopify_order_number: shopifyOrderNumber.trim() } : {}) }),
    onSuccess: (execution) => setDraftExecutionId(execution.id),
  });
  const draftExecution = useQuery({
    queryKey: aiQueryKeys.execution(draftExecutionId),
    queryFn: () => getAIExecution(draftExecutionId!),
    enabled: Boolean(draftExecutionId),
    refetchInterval: (query) => {
      const active = ["queued", "running"].includes(query.state.data?.status ?? "");
      return active && typeof document !== "undefined" && document.visibilityState === "visible" ? 1500 : false;
    },
    refetchIntervalInBackground: false,
  });

  useEffect(() => {
    if (conversations.data?.length === 1 && !selectedConversation) chooseConversation(conversations.data[0].id);
    // A multi-thread ticket must stay unselected until the user chooses.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversations.data]);

  useEffect(() => {
    if (!showDetails) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowDetails(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [showDetails]);

  function chooseConversation(id: string) {
    setSelectedConversation(id);
    setComposeMode("reply");
    setDraftExecutionId(undefined);
    createDraft.reset();
    read.mutate(id);
  }
  function selectTicket(item: InboxItem) {
    setSelectedTicket(item);
    setSelectedConversation("");
    setShopifyOrderNumber("");
    setDraftExecutionId(undefined);
    createDraft.reset();
    setShowDetails(false);
  }

  const canReply = ["owner", "admin", "agent"].includes(me.data?.role ?? "");

  return <div className="relative">
    <div className="relative flex h-[calc(100dvh-4rem)] min-h-[520px] flex-col overflow-hidden bg-white lg:flex-row">
      <section aria-label="Inbox tickets" className={`${activeTicket ? "hidden lg:flex" : "flex"} w-full flex-col border-r border-slate-200 lg:w-[320px] xl:w-[350px]`}>
        <header className="space-y-4 border-b border-slate-200 p-5">
          <div className="flex items-start justify-between"><div><p className="text-xs font-bold uppercase tracking-[.16em] text-blue-700">Support workspace</p><h1 className="mt-1 text-2xl font-bold">Inbox</h1></div><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">{rows.length}{inbox.hasNextPage ? "+" : ""} tickets</span></div>
          <label className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5"><Search size={16} className="text-slate-400"/><span className="sr-only">Search inbox</span><input className="min-w-0 flex-1 bg-transparent text-sm outline-none" placeholder="Search tickets or customers" value={searchDraft} onChange={(e) => setSearchDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") setFilters((value) => ({ ...value, search: searchDraft })); }}/><button type="button" className="text-xs font-semibold text-blue-700" onClick={() => setFilters((value) => ({ ...value, search: searchDraft }))}>Search</button></label>
          <div className="grid grid-cols-3 gap-2"><FilterButton active={filters.scope === "all"} onClick={() => setFilters({ ...filters, scope: "all" })}>All</FilterButton><FilterButton active={filters.scope === "mine"} onClick={() => setFilters({ ...filters, scope: "mine" })}>Mine</FilterButton><FilterButton active={filters.scope === "unassigned"} onClick={() => setFilters({ ...filters, scope: "unassigned" })}>Unassigned</FilterButton></div>
          <div className="grid grid-cols-2 gap-2"><Select aria-label="Filter by status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All statuses</option>{["open", "pending", "resolved", "closed"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</Select><Select aria-label="Filter by priority" value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value })}><option value="">All priorities</option>{["low", "normal", "high", "urgent"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</Select></div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">
          {inbox.isPending && <div className="space-y-3 p-4">{[1,2,3,4].map((i) => <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100"/>)}</div>}
          {inbox.isError && <div role="alert" className="m-4 rounded-xl bg-red-50 p-4 text-sm text-red-700">Could not load the inbox. <button className="font-semibold underline" onClick={() => inbox.refetch()}>Try again</button></div>}
          {!inbox.isPending && !inbox.isError && rows.length === 0 && <div className="p-8 text-center"><p className="font-semibold">No tickets match</p><p className="mt-1 text-sm text-slate-500">Change a filter or clear your search.</p></div>}
          {rows.map((item) => <button key={item.ticketId} onClick={() => selectTicket(item)} aria-pressed={activeTicket?.ticketId === item.ticketId} className={`w-full border-b border-slate-100 p-4 text-left transition hover:bg-slate-50 ${activeTicket?.ticketId === item.ticketId ? "bg-blue-50/70" : ""}`}><div className="flex items-start gap-3"><Avatar name={item.customer.name}/><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><p className="truncate text-sm font-semibold">{item.customer.name}</p><time className="shrink-0 text-[11px] text-slate-400">{relative(item.updatedAt)}</time></div><p className="mt-1 truncate text-sm font-medium text-slate-800">{item.subject}</p><p className="mt-1 truncate text-xs text-slate-500">{item.latestMessage?.preview ?? "No messages yet"}</p><div className="mt-2 flex items-center gap-2"><StatusPill value={item.status}/><span className="text-[11px] capitalize text-slate-500">{item.priority}</span>{item.unreadCount > 0 && <span aria-label={`${item.unreadCount} unread customer messages`} title={`${item.unreadCount} unread customer messages`} className="ml-auto rounded-full bg-blue-700 px-2 py-0.5 text-[10px] font-bold text-white">{item.unreadCount} new</span>}</div></div></div></button>)}
          {inbox.hasNextPage && <div className="p-4"><Button variant="secondary" className="w-full" disabled={inbox.isFetchingNextPage} onClick={() => inbox.fetchNextPage()}>{inbox.isFetchingNextPage ? "Loading…" : "Load more"}</Button></div>}
        </div>
      </section>

      <section aria-label="Conversation thread" className={`${activeTicket ? "flex" : "hidden lg:flex"} relative min-w-0 flex-1 flex-col`}>
        {!activeTicket ? <EmptyThread/> : <>
          <header className="flex min-h-[76px] flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3 sm:px-6"><button className="rounded-lg p-2 hover:bg-slate-100 lg:hidden" aria-label="Back to inbox" onClick={() => { setSelectedTicket(null); setShowDetails(false); }}><ArrowLeft size={18}/></button><Avatar name={activeTicket.customer.name}/><div className="min-w-0 flex-1"><p className="truncate font-semibold">{activeTicket.customer.name}</p><p className="truncate text-xs text-slate-500">{activeTicket.subject}</p></div>{conversations.data && conversations.data.length > 1 && <Select aria-label="Choose conversation" className="max-w-44 text-xs" value={selectedConversation} onChange={(event) => chooseConversation(event.target.value)}><option value="" disabled>Choose conversation</option>{conversations.data.map((conversation, index) => <option key={conversation.id} value={conversation.id}>Conversation {conversations.data!.length - index} · {titleCase(conversation.channel)}</option>)}</Select>}<StatusPill value={activeTicket.status}/><button className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 xl:hidden" onClick={() => setShowDetails(true)} aria-label="Open ticket and customer details"><PanelRight size={15}/>Details</button></header>
          <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50/60 p-4 sm:p-6" aria-live="polite">
            {conversations.isPending && <p className="text-sm text-slate-500">Loading conversations…</p>}
            {conversations.isError && <p role="alert" className="text-sm text-red-700">Could not load conversations for this ticket.</p>}
            {conversations.data?.length === 0 && <div className="mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white p-6 text-center"><p className="font-semibold">No conversation yet</p><p className="mt-1 text-sm text-slate-500">This ticket does not have a message thread to display.</p></div>}
            {read.isError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">Could not update this conversation’s read status.</p>}
            {conversations.data && conversations.data.length > 1 && !selectedConversation && <div className="mx-auto max-w-xl rounded-2xl border border-blue-200 bg-white p-6 shadow-sm"><p className="font-semibold">Choose a conversation</p><p className="mt-1 text-sm text-slate-500">This ticket has separate conversation histories. Select one to view its messages.</p><div className="mt-4 space-y-2">{conversations.data.map((conversation, index) => <button key={conversation.id} onClick={() => chooseConversation(conversation.id)} className="flex w-full items-center justify-between rounded-xl border border-slate-200 p-3 text-left hover:border-blue-300 hover:bg-blue-50"><span><span className="block text-sm font-semibold">Conversation {conversations.data!.length - index}</span><span className="text-xs text-slate-500">{titleCase(conversation.channel)} · updated {formatDateTime(conversation.updated_at)}</span></span><span aria-hidden className="text-blue-700">→</span></button>)}</div></div>}
            {selectedConversation && messages.isPending && <div className="h-32 animate-pulse rounded-2xl bg-slate-200"/>}
            {selectedConversation && messages.isError && <p role="alert" className="text-sm text-red-700">Could not load this conversation.</p>}
            {notes.isError && <p role="alert" className="text-sm text-red-700">Could not load internal notes.</p>}
            {[...(messages.data ?? []), ...(notes.data ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id)).map((message) => {
              const isNote = message.sender_type === "internal_note";
              const fromAgent = message.sender_type === "agent" || message.sender_type === "assistant";
              const senderName = message.sender_type === "assistant" ? "SupportPilot AI" : message.sender_name ?? titleCase(message.sender_type);
              return <motion.div key={message.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }} className={`flex ${isNote || !fromAgent ? "justify-start" : "justify-end"}`}><article aria-label={isNote ? "Internal note" : message.sender_type === "assistant" ? "AI reply" : undefined} className={`max-w-[88%] rounded-2xl px-4 py-3 sm:max-w-[72%] ${isNote ? "border border-amber-200 bg-amber-50 text-amber-950" : fromAgent ? "rounded-br-md bg-blue-700 text-white" : "rounded-bl-md border border-slate-200 bg-white"}`}><div className={`mb-1.5 flex gap-2 text-xs ${isNote ? "text-amber-800" : fromAgent ? "text-blue-100" : "text-slate-500"}`}><span className="font-semibold">{isNote ? `Internal note · ${message.sender_name ?? "Teammate"}` : senderName}</span><time>{formatDateTime(message.created_at)}</time></div><p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p></article></motion.div>;
            })}
            {isWidgetConversation && widgetAI.data && <div className={`mx-auto w-full max-w-2xl rounded-xl border p-3 text-sm ${widgetAI.data.status === "failed" ? "border-red-200 bg-red-50 text-red-800" : widgetAI.data.status === "escalated" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-blue-200 bg-blue-50 text-blue-900"}`} role={widgetAI.data.status === "processing" ? "status" : "note"}>
              <p className="font-semibold">AI reply · {widgetAI.data.status.replace("_", " ")}</p>
              {widgetAI.data.safe_summary && <p className="mt-1 text-xs">{widgetAI.data.safe_summary}</p>}
              {widgetAI.data.status === "processing" && <p className="mt-1 text-xs">Preparing a grounded response…</p>}
              {widgetAI.data.status === "draft_ready" && widgetAI.data.draft && <><p className="mt-2 whitespace-pre-wrap">{widgetAI.data.draft}</p><Button type="button" size="sm" variant="secondary" className="mt-2" onClick={() => { setComposeMode("reply"); setReply(widgetAI.data?.draft ?? ""); }}>Add draft to reply</Button></>}
              {widgetAI.data.citations.length > 0 && <p className="mt-2 text-xs">Sources: {widgetAI.data.citations.map((citation) => `${citation.document_name} · section ${citation.chunk_index + 1}`).join(", ")}</p>}
            </div>}
            {selectedConversation && messages.data?.length === 0 && notes.data?.length === 0 && !notes.isPending && <p className="py-10 text-center text-sm text-slate-500">No messages or notes in this conversation.</p>}
          </div>
          {selectedConversation && <>
            {composeMode === "reply" && (createDraft.isError || draftExecution.isError) && <p role="alert" className="border-t border-red-100 bg-red-50 px-4 py-2 text-sm text-red-700">{createDraft.error?.message ?? "Draft status could not be refreshed."}</p>}
            {composeMode === "reply" && draftExecution.data && ["queued", "running"].includes(draftExecution.data.status) && <p role="status" className="flex items-center gap-2 border-t border-blue-100 bg-blue-50 px-4 py-2 text-sm text-blue-800"><LoaderCircle size={15} className="animate-spin"/>Finding sources and preparing an unsent draft…</p>}
            {composeMode === "reply" && draftExecution.data?.status === "failed" && <p role="alert" className="border-t border-amber-100 bg-amber-50 px-4 py-2 text-sm text-amber-800">The AI draft could not be completed. Your reply was not sent.</p>}
            {composeMode === "reply" && draftExecution.data?.status === "succeeded" && <div className="border-t border-slate-200 bg-slate-50 px-4 py-3 sm:px-5">
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-semibold text-slate-700">AI draft · review before sending</p><Button size="sm" variant="secondary" onClick={() => setReply(draftExecution.data?.draft ?? "")}>Add to reply</Button></div>
              <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-sm leading-5 text-slate-600">{draftExecution.data.draft}</p>
              {draftExecution.data.citations.length > 0 && <p className="mt-2 text-xs text-blue-700">Sources: {draftExecution.data.citations.map((citation) => `${citation.document_name} · section ${citation.chunk_index + 1}`).join(", ")}</p>}
              {draftExecution.data.citations.length === 0 && <p className="mt-2 text-xs text-amber-700">No matching knowledge sources were found. Verify the draft carefully.</p>}
            </div>}
            <form onSubmit={(event) => { event.preventDefault(); if (reply.trim()) send.mutate(); }} className={`border-t p-4 sm:p-5 ${composeMode === "note" ? "border-amber-200 bg-amber-50/60" : "border-slate-200 bg-white"}`}>
              <div className="mb-3 flex gap-2" role="group" aria-label="Message type"><Button type="button" size="sm" variant={composeMode === "reply" ? "primary" : "secondary"} aria-pressed={composeMode === "reply"} onClick={() => setComposeMode("reply")}>Reply</Button><Button type="button" size="sm" variant={composeMode === "note" ? "primary" : "secondary"} aria-pressed={composeMode === "note"} onClick={() => { setComposeMode("note"); setDraftExecutionId(undefined); }}>Internal note</Button></div>
              {composeMode === "note" && <p className="mb-2 text-xs font-medium text-amber-900">Only workspace teammates can see this note. It will not be sent to the customer.</p>}
              {composeMode === "reply" && <label className="mb-3 block max-w-xs text-xs font-medium text-slate-600">Add a verified Shopify order to the AI draft <input aria-label="Shopify order number for AI draft" value={shopifyOrderNumber} onChange={(event) => setShopifyOrderNumber(event.target.value)} placeholder="#1001 (optional)" className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"/></label>}
              <Textarea aria-label={composeMode === "note" ? "Write an internal note" : "Write a reply"} placeholder={!canReply ? "Your role has read-only access" : composeMode === "note" ? "Write a private note for your team…" : "Reply to the customer…"} value={reply} disabled={!canReply || send.isPending} onChange={(event) => setReply(event.target.value)} className="min-h-24"/>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-slate-500">{composeMode === "note" ? "Private to your workspace" : "Messages are sent as you."}</span><div className="flex gap-2">{composeMode === "reply" && <Button type="button" variant="secondary" disabled={!canReply || createDraft.isPending || Boolean(draftExecution.data && ["queued", "running"].includes(draftExecution.data.status))} onClick={() => createDraft.mutate()}><Sparkles size={15}/>{createDraft.isPending ? "Starting…" : "Draft with AI"}</Button>}<Button type="submit" disabled={!canReply || !reply.trim() || send.isPending}>{send.isPending ? composeMode === "note" ? "Saving…" : "Sending…" : composeMode === "note" ? "Add note" : "Send reply"}{composeMode === "reply" && <Send size={15}/>}</Button></div></div>
              {send.isError && <p role="alert" className="mt-2 text-sm text-red-700">{send.error instanceof Error ? send.error.message : "Message could not be sent."}</p>}
            </form>
          </>}
        </>}
      </section>

      {activeTicket && <aside aria-label="Customer context" className="hidden w-[320px] shrink-0 border-l border-slate-200 xl:block"><CustomerContextPanel item={activeTicket} role={me.data?.role ?? "viewer"}/></aside>}
      {activeTicket && showDetails && <div role="dialog" aria-modal="true" aria-label="Ticket and customer details" className="absolute inset-0 z-30 bg-slate-950/30 xl:hidden" onClick={() => setShowDetails(false)}><div className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-white shadow-2xl" onClick={(event) => event.stopPropagation()}><header className="flex h-14 items-center justify-between border-b border-slate-200 px-4"><p className="font-semibold">Ticket details</p><button autoFocus onClick={() => setShowDetails(false)} className="rounded-lg px-3 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50">Back to conversation</button></header><div className="min-h-0 flex-1"><CustomerContextPanel item={activeTicket} role={me.data?.role ?? "viewer"}/></div></div></div>}
    </div>
  </div>;
}

function FilterButton({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) { return <button onClick={onClick} className={`rounded-lg px-2 py-2 text-xs font-semibold ${active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>{children}</button>; }
function Avatar({ name }: { name: string }) { return <span className="grid size-10 shrink-0 place-items-center rounded-full bg-violet-100 text-sm font-bold text-violet-800">{name.trim().slice(0, 1).toUpperCase()}</span>; }
function StatusPill({ value }: { value: string }) { const colors: Record<string, string> = { open: "bg-emerald-50 text-emerald-700", pending: "bg-amber-50 text-amber-700", resolved: "bg-blue-50 text-blue-700", closed: "bg-slate-100 text-slate-600" }; return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${colors[value] ?? colors.closed}`}>{value}</span>; }
function EmptyThread() { return <div className="grid flex-1 place-items-center p-8 text-center"><div><span className="mx-auto grid size-14 place-items-center rounded-2xl bg-blue-50 text-blue-700"><Send size={22}/></span><h2 className="mt-4 text-lg font-semibold">Select a ticket</h2><p className="mt-1 max-w-xs text-sm text-slate-500">Choose a conversation from your inbox to read and reply.</p></div></div>; }
function titleCase(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function relative(value: string) { const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60_000)); if (minutes < 1) return "now"; if (minutes < 60) return `${minutes}m`; const hours = Math.floor(minutes / 60); if (hours < 24) return `${hours}h`; return `${Math.floor(hours / 24)}d`; }
