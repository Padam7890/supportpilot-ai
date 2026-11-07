"use client";

import { SupportTraceLink } from "@/components/support-trace-link";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import Link from "next/link";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, Check, CheckCircle2, Download, LoaderCircle, Paperclip, PanelRight, RefreshCw, Search, Send, Sparkles, Trash2, UserRoundPlus, UserRound } from "lucide-react";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/input";
import { listConversations, listInternalNotes, listMessages, sendInternalNote, sendMessage, startConversation, updateConversationAIAgent, updateConversationAIMode } from "@/features/conversations/api/conversation-api";
import { sendMessageSchema } from "@/features/conversations/schemas/conversation.schema";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { aiAgentsKey, listAIAgents } from "@/features/ai/api/ai-agent-api";
import { getInbox, inboxQueryKeys, markConversationRead } from "../api/inbox-api";
import type { InboxFilters } from "../api/inbox-api";
import type { InboxItem } from "../types/inbox.types";
import { formatDateTime } from "@/lib/utils";
import { CustomerContextPanel } from "./customer-context-panel";
import { aiQueryKeys, createReplyDraft, getAIExecution, getWidgetAIReplyStatus } from "@/features/ai/api/ai-api";
import { assignTicketToMe, updateTicket } from "@/features/tickets/api/ticket-api";
import { ShopifyCancellationPanel } from "@/features/commerce-actions/components/shopify-cancellation-panel";
import { formatInboxRequestError } from "../utils/request-error";
import { inboxQueryRetryDelay, shouldRetryInboxQuery } from "../utils/query-retry";
import { activeTeamsQueryKey, listActiveTeams } from "@/features/organization/api/team-api";
import { listSavedReplies, savedRepliesQueryKey } from "@/features/saved-replies/api/saved-replies-api";
import { conversationAttachmentsKey, deleteConversationAttachment, downloadConversationAttachment, listConversationAttachments, uploadConversationAttachment } from "@/features/attachments/api/conversation-attachment-api";
import { expandSavedReplyAtCursor } from "@/features/saved-replies/utils/expand-shortcut";
import { getAttachmentValidationError } from "@/features/attachments/utils/validate-attachment";

const initialFilters: InboxFilters = { scope: "all", status: "", priority: "", teamId: "", search: "", needsApproval: false, unreadOnly: false };

export function InboxWorkspace() {
  const client = useQueryClient();
  const [filters, setFilters] = useState(initialFilters);
  const [searchDraft, setSearchDraft] = useState("");
  const [selectedTicket, setSelectedTicket] = useState<InboxItem | null>(null);
  const [selectedConversation, setSelectedConversation] = useState("");
  const [showDetails, setShowDetails] = useState(false);
  const [reply, setReply] = useState("");
  const replyInputRef = useRef<HTMLTextAreaElement>(null);
  const [attachmentValidationError, setAttachmentValidationError] = useState<string | null>(null);
  const [fileDropActive, setFileDropActive] = useState(false);
  const attachmentDetailsRef = useRef<HTMLDetailsElement>(null);
  const [shopifyOrderNumber, setShopifyOrderNumber] = useState("");
  const [composeMode, setComposeMode] = useState<"reply" | "note">("reply");
  const [draftExecutionId, setDraftExecutionId] = useState<string>();
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const teams = useQuery({ queryKey: activeTeamsQueryKey, queryFn: listActiveTeams });
  const inbox = useInfiniteQuery({
    queryKey: inboxQueryKeys.page(filters),
    queryFn: ({ pageParam }) => getInbox(filters, pageParam),
    initialPageParam: undefined as string | undefined,
    retry: shouldRetryInboxQuery,
    retryDelay: inboxQueryRetryDelay,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 20_000 : false,
    refetchIntervalInBackground: false,
  });
  const rows = useMemo(() => inbox.data?.pages.flatMap((page) => page.items) ?? [], [inbox.data]);
  const hasActiveFilters = filters.scope !== "all"
    || Boolean(filters.status)
    || Boolean(filters.priority)
    || Boolean(filters.teamId)
    || Boolean(filters.search)
    || filters.needsApproval
    || filters.unreadOnly
    || Boolean(searchDraft);
  const activeTicket = selectedTicket ? rows.find((item) => item.ticketId === selectedTicket.ticketId) ?? selectedTicket : null;
  const conversations = useQuery({
    queryKey: inboxQueryKeys.conversations(activeTicket?.ticketId),
    queryFn: () => listConversations(activeTicket!.ticketId),
    enabled: Boolean(activeTicket),
    retry: shouldRetryInboxQuery,
    retryDelay: inboxQueryRetryDelay,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 10_000 : false,
    refetchIntervalInBackground: false,
  });
  const activeConversationId = !selectedConversation && conversations.data?.length === 1
    ? conversations.data[0].id
    : conversations.data?.some((item) => item.id === selectedConversation)
      ? selectedConversation
      : "";
  const startThread = useMutation({
    mutationFn: () => startConversation(activeTicket!.ticketId),
    onSuccess: async (conversation) => {
      client.setQueryData(
        inboxQueryKeys.conversations(activeTicket?.ticketId),
        (current: typeof conversations.data) => [...(current ?? []), conversation],
      );
      chooseConversation(conversation.id);
      await client.invalidateQueries({ queryKey: inboxQueryKeys.conversations(activeTicket?.ticketId) });
    },
  });
  const messages = useQuery({
    queryKey: inboxQueryKeys.messages(activeConversationId || undefined),
    queryFn: () => listMessages(activeConversationId),
    enabled: Boolean(activeConversationId),
    retry: shouldRetryInboxQuery,
    retryDelay: inboxQueryRetryDelay,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 10_000 : false,
    refetchIntervalInBackground: false,
  });
  const notes = useQuery({
    queryKey: ["internal-notes", activeConversationId || undefined],
    queryFn: () => listInternalNotes(activeConversationId),
    enabled: Boolean(activeConversationId),
    retry: shouldRetryInboxQuery,
    retryDelay: inboxQueryRetryDelay,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 10_000 : false,
    refetchIntervalInBackground: false,
  });
  const latestMessage = useMemo(() => (messages.data ?? []).reduce<NonNullable<typeof messages.data>[number] | null>(
    (latest, message) => !latest
      || message.created_at > latest.created_at
      || (message.created_at === latest.created_at && message.id > latest.id)
      ? message
      : latest,
    null,
  ), [messages.data]);
  const isWidgetConversation = conversations.data?.some((item) => item.id === activeConversationId && item.channel === "shopify_widget") ?? false;
  const selectedThread = conversations.data?.find((item) => item.id === activeConversationId);
  const aiAgents = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents, enabled: isWidgetConversation, staleTime: 60_000 });
  const changeAIMode = useMutation({
    mutationFn: (mode: "ai" | "human") => updateConversationAIMode(activeConversationId, mode),
    onSuccess: async (updated) => {
      client.setQueryData(inboxQueryKeys.conversations(activeTicket?.ticketId), (current: typeof conversations.data) => current?.map((item) => item.id === updated.id ? updated : item));
      await Promise.all([
        client.invalidateQueries({ queryKey: inboxQueryKeys.conversations(activeTicket?.ticketId) }),
        client.invalidateQueries({ queryKey: ["widget-ai-reply", activeConversationId] }),
      ]);
    },
  });
  const changeConversationAgent = useMutation({
    mutationFn: (agentId: string | null) => updateConversationAIAgent(activeConversationId, agentId),
    onSuccess: async (updated) => {
      client.setQueryData(inboxQueryKeys.conversations(activeTicket?.ticketId), (current: typeof conversations.data) => current?.map((item) => item.id === updated.id ? updated : item));
      setDraftExecutionId(undefined);
      await Promise.all([
        client.invalidateQueries({ queryKey: inboxQueryKeys.conversations(activeTicket?.ticketId) }),
        client.invalidateQueries({ queryKey: ["widget-ai-reply", activeConversationId] }),
      ]);
    },
  });
  const widgetAI = useQuery({
    queryKey: ["widget-ai-reply", activeConversationId],
    queryFn: () => getWidgetAIReplyStatus(activeConversationId),
    enabled: Boolean(activeConversationId && isWidgetConversation),
    retry: shouldRetryInboxQuery,
    retryDelay: inboxQueryRetryDelay,
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 4000 : false,
    refetchIntervalInBackground: false,
  });
  const read = useMutation({ mutationFn: markConversationRead, onSuccess: async () => {
    await client.invalidateQueries({ queryKey: ["inbox"] });
  } });
  const lastReadCursor = useRef("");
  const transcriptRef = useRef<HTMLDivElement>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const followLatestMessage = useRef(true);
  const lastTranscriptConversation = useRef("");
  useEffect(() => {
    const markLatestAsRead = () => {
      if (!activeConversationId || !latestMessage || document.visibilityState !== "visible") return;
      const cursor = `${activeConversationId}:${latestMessage.id}`;
      if (lastReadCursor.current === cursor) return;
      lastReadCursor.current = cursor;
      read.mutate(activeConversationId);
    };
    markLatestAsRead();
    document.addEventListener("visibilitychange", markLatestAsRead);
    return () => document.removeEventListener("visibilitychange", markLatestAsRead);
  }, [activeConversationId, latestMessage?.id, read]);
  useEffect(() => {
    if (!activeConversationId) return;
    if (lastTranscriptConversation.current !== activeConversationId) {
      lastTranscriptConversation.current = activeConversationId;
      followLatestMessage.current = true;
    }
    if (followLatestMessage.current) {
      transcriptEndRef.current?.scrollIntoView({ block: "end", behavior: "auto" });
    }
  }, [activeConversationId, messages.data?.length, notes.data?.length, widgetAI.data?.status]);
  const send = useMutation({ mutationFn: () => composeMode === "note"
    ? sendInternalNote(activeConversationId, sendMessageSchema.parse({ content: reply }).content)
    : sendMessage(activeConversationId, sendMessageSchema.parse({ content: reply })), onSuccess: async () => {
    setReply("");
    setDraftExecutionId(undefined);
    await Promise.all([client.invalidateQueries({ queryKey: inboxQueryKeys.messages(activeConversationId) }), client.invalidateQueries({ queryKey: ["internal-notes", activeConversationId] }), client.invalidateQueries({ queryKey: ["inbox"] }), client.invalidateQueries({ queryKey: ["widget-ai-reply", activeConversationId] })]);
  } });
  const approveWidgetDraft = useMutation({
    mutationFn: () => sendMessage(activeConversationId, sendMessageSchema.parse({ content: widgetAI.data?.draft ?? "" })),
    onSuccess: async () => {
      setReply("");
      await Promise.all([
        client.invalidateQueries({ queryKey: inboxQueryKeys.messages(activeConversationId) }),
        client.invalidateQueries({ queryKey: ["widget-ai-reply", activeConversationId] }),
        client.invalidateQueries({ queryKey: ["inbox"] }),
      ]);
    },
  });
  const createDraft = useMutation({
    mutationFn: () => createReplyDraft({ conversation_id: activeConversationId, ...(shopifyOrderNumber.trim() ? { shopify_order_number: shopifyOrderNumber.trim() } : {}) }),
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
    if (!showDetails) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowDetails(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [showDetails]);

  function chooseConversation(id: string) {
    setReply("");
    setSelectedConversation(id);
    setAttachmentValidationError(null);
    setFileDropActive(false);
    setComposeMode("reply");
    setDraftExecutionId(undefined);
    createDraft.reset();
  }
  function changeFilters(update: (current: InboxFilters) => InboxFilters) {
    setFilters(update);
    setSelectedTicket(null);
    setSelectedConversation("");
    setShowDetails(false);
    setReply("");
    setAttachmentValidationError(null);
    setFileDropActive(false);
    setShopifyOrderNumber("");
    setDraftExecutionId(undefined);
    setComposeMode("reply");
    createDraft.reset();
  }
  function clearFilters() {
    setSearchDraft("");
    changeFilters(() => initialFilters);
  }
  function selectTicket(item: InboxItem) {
    setReply("");
    setComposeMode("reply");
    setSelectedTicket(item);
    setSelectedConversation("");
    setAttachmentValidationError(null);
    setFileDropActive(false);
    setShopifyOrderNumber("");
    setDraftExecutionId(undefined);
    createDraft.reset();
    setShowDetails(false);
  }

  const canReply = ["owner", "admin", "agent"].includes(me.data?.role ?? "");
  const savedReplies = useQuery({
    queryKey: savedRepliesQueryKey(me.data?.organization_id),
    queryFn: () => listSavedReplies(),
    enabled: Boolean(activeConversationId && me.data?.organization_id) && composeMode === "reply" && canReply,
    staleTime: 60_000,
  });
  const attachmentsKey = conversationAttachmentsKey(me.data?.organization_id, activeConversationId || undefined);
  const attachments = useQuery({
    queryKey: attachmentsKey,
    queryFn: () => listConversationAttachments(activeConversationId),
    enabled: Boolean(activeConversationId && me.data?.organization_id),
  });
  const uploadAttachment = useMutation({
    mutationFn: ({ conversationId, file }: { conversationId: string; file: File }) => uploadConversationAttachment(conversationId, file),
    onSuccess: async (_attachment, variables) => client.invalidateQueries({
      queryKey: conversationAttachmentsKey(me.data?.organization_id, variables.conversationId),
    }),
  });
  const removeAttachment = useMutation({
    mutationFn: ({ attachmentId }: { attachmentId: string; conversationId: string }) => deleteConversationAttachment(attachmentId),
    onSuccess: async (_result, variables) => client.invalidateQueries({
      queryKey: conversationAttachmentsKey(me.data?.organization_id, variables.conversationId),
    }),
  });
  const downloadAttachment = useMutation({
    mutationFn: ({ attachmentId }: { attachmentId: string; conversationId: string }) => downloadConversationAttachment(attachmentId),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  const handleAttachmentDrop = (event: DragEvent<HTMLDivElement>) => {
    if (!canReply || !activeConversationId || !Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    setFileDropActive(false);
    attachmentDetailsRef.current?.setAttribute("open", "");
    const files = Array.from(event.dataTransfer.files);
    if (files.length !== 1) {
      setAttachmentValidationError("Drop one file at a time.");
      return;
    }
    if (uploadAttachment.isPending) {
      setAttachmentValidationError("Wait for the current upload to finish before adding another file.");
      return;
    }
    const validationError = getAttachmentValidationError(files[0]);
    if (validationError) {
      setAttachmentValidationError(validationError);
      return;
    }
    setAttachmentValidationError(null);
    uploadAttachment.mutate({ conversationId: activeConversationId, file: files[0] });
  };
  const refreshTicket = async () => {
    await Promise.all([client.invalidateQueries({ queryKey: ["inbox"] }), client.invalidateQueries({ queryKey: ["ticket-activity", activeTicket?.ticketId] })]);
  };
  const claimTicket = useMutation({ mutationFn: () => assignTicketToMe(activeTicket!.ticketId), onSuccess: refreshTicket });
  const resolveTicket = useMutation({ mutationFn: () => updateTicket(activeTicket!.ticketId, { status: activeTicket!.status === "resolved" ? "open" : "resolved" }), onSuccess: refreshTicket });

  return <div className="relative h-full min-h-0">
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-slate-50 lg:flex-row">
      <section aria-label="Inbox tickets" className={`${activeTicket ? "hidden lg:flex" : "flex"} w-full flex-col border-r border-slate-200 lg:w-[300px] lg:shrink-0 2xl:w-[340px]`}>
        <header className="space-y-4 border-b border-slate-200 bg-slate-50 px-4 pb-4 pt-5">
          <div className="flex items-center justify-between"><div><h1 className="text-[21px] font-bold tracking-tight text-slate-900">Inbox</h1><p className="mt-1 text-xs text-slate-500">Showing {rows.length}{inbox.hasNextPage ? "+" : ""} tickets</p></div><Button size="sm" variant="secondary" aria-label="Refresh inbox" title="Refresh inbox" onClick={() => inbox.refetch()}><RefreshCw size={15}/></Button></div>
          <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-3 shadow-sm focus-within:border-blue-500/50 focus-within:ring-2 focus-within:ring-blue-500/10"><Search size={16} className="shrink-0 text-slate-400"/><span className="sr-only">Search inbox</span><input className="min-w-0 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-500" placeholder="Search customers or messages" value={searchDraft} onChange={(e) => setSearchDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") changeFilters((value) => ({ ...value, search: searchDraft })); }}/><button type="button" aria-label="Apply inbox search" className="text-xs font-semibold text-blue-700" onClick={() => changeFilters((value) => ({ ...value, search: searchDraft }))}>Search</button></label>
          <div className="flex flex-wrap gap-1.5 pb-0.5" aria-label="Inbox views">
            {(["all", "mine", "unassigned", "my_teams"] as const).map((scope) => <button key={scope} aria-pressed={filters.scope === scope && !filters.needsApproval && !filters.unreadOnly} onClick={() => changeFilters((value) => ({ ...value, scope, needsApproval: false, unreadOnly: false }))} className={`shrink-0 rounded-full px-3 py-1.5 text-[11px] font-semibold transition ${filters.scope === scope && !filters.needsApproval && !filters.unreadOnly ? "bg-blue-700 text-[var(--text-on-accent)] shadow-sm" : "bg-white text-slate-600 hover:bg-slate-100"}`}>{scope === "mine" ? "Mine" : scope === "all" ? "All" : scope === "unassigned" ? "Unassigned" : "My teams"}</button>)}
            <button aria-pressed={filters.needsApproval} onClick={() => changeFilters((value) => ({ ...value, needsApproval: !value.needsApproval, unreadOnly: false }))} className={`shrink-0 rounded-full px-3 py-1.5 text-[11px] font-semibold transition ${filters.needsApproval ? "bg-amber-50 text-amber-700" : "bg-white text-slate-600 hover:bg-slate-100"}`}>Needs approval</button>
            <button aria-pressed={filters.unreadOnly} onClick={() => changeFilters((value) => ({ ...value, unreadOnly: !value.unreadOnly, needsApproval: false }))} className={`shrink-0 rounded-full px-3 py-1.5 text-[11px] font-semibold transition ${filters.unreadOnly ? "bg-blue-50 text-blue-700" : "bg-white text-slate-600 hover:bg-slate-100"}`}>Unread</button>
          </div>
          <div className="flex flex-wrap items-center gap-2"><Select aria-label="Filter by status" className="py-1.5 text-xs" value={filters.status} onChange={(e) => changeFilters((value) => ({ ...value, status: e.target.value }))}><option value="">All statuses</option>{["open", "pending", "resolved", "closed"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</Select><Select aria-label="Filter by priority" className="py-1.5 text-xs" value={filters.priority} onChange={(e) => changeFilters((value) => ({ ...value, priority: e.target.value }))}><option value="">Any priority</option>{["low", "normal", "high", "urgent"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</Select><Select aria-label="Filter by team" className="py-1.5 text-xs" value={filters.teamId ?? ""} onChange={(e) => changeFilters((value) => ({ ...value, teamId: e.target.value }))}><option value="">All teams</option>{teams.data?.filter((team) => team.is_active).map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</Select>{teams.isPending && <span role="status" className="text-xs text-slate-500">Loading teams…</span>}{teams.isError && <span role="status" className="text-xs text-amber-700">Team filter unavailable</span>}{hasActiveFilters && <button type="button" onClick={clearFilters} className="shrink-0 rounded-lg px-2 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-50">Clear</button>}</div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">
          {inbox.isPending && <div className="space-y-3 p-4">{[1,2,3,4].map((i) => <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100"/>)}</div>}
          {inbox.isError && <div role="alert" className="m-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"><p className="font-semibold">Could not load the inbox</p><p className="mt-1 break-words text-xs">{formatInboxRequestError(inbox.error, "The inbox request failed.")}</p><button className="mt-2 font-semibold underline" onClick={() => inbox.refetch()}>Try again</button></div>}
          {!inbox.isPending && !inbox.isError && rows.length === 0 && <div className="p-8 text-center"><p className="font-semibold">No tickets match</p><p className="mt-1 text-sm text-slate-500">Change a filter or clear your search.</p></div>}
          {rows.map((item) => <button key={item.ticketId} onClick={() => selectTicket(item)} aria-pressed={activeTicket?.ticketId === item.ticketId} className={`mx-2 my-1.5 w-[calc(100%-1rem)] rounded-xl border border-transparent px-3 py-3.5 text-left transition hover:border-slate-200 hover:bg-white ${activeTicket?.ticketId === item.ticketId ? "border-slate-200 bg-white shadow-sm" : "bg-transparent"}`}><div className="flex items-start gap-3"><Avatar name={item.customer.name}/><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><p className={`truncate text-sm ${item.unreadCount ? "font-bold text-slate-950" : "font-semibold text-slate-700"}`}>{item.customer.name}</p><time className="shrink-0 text-[11px] text-slate-500">{relative(item.updatedAt)}</time></div><p className="mt-1 truncate text-[13px] font-medium text-slate-800">{item.subject}</p><p className="mt-1 truncate text-xs text-slate-500">{item.latestMessage?.preview ?? "No messages yet"}</p><div className="mt-2 flex flex-wrap items-center gap-2"><StatusPill value={item.status}/><span className="text-[11px] capitalize text-slate-500">{item.priority}</span>{item.firstResponseSla && <SlaPill sla={item.firstResponseSla}/>}{item.team && <span className={`max-w-28 truncate rounded-full px-2 py-0.5 text-[10px] font-medium ${item.team.is_active ? "bg-violet-50 text-violet-700" : "bg-slate-100 text-slate-500"}`} title={item.team.is_active ? `Team: ${item.team.name}` : `Inactive team: ${item.team.name}`}>{item.team.name}{item.team.is_active ? "" : " · inactive"}</span>}{item.assignee && <span className="ml-auto max-w-24 truncate text-[10px] text-slate-500">{item.assignee.name}</span>}{item.unreadCount > 0 && <span aria-label={`${item.unreadCount} unread customer messages`} title={`${item.unreadCount} unread customer messages`} className="ml-auto rounded-full bg-[var(--accent)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-on-accent)]">{item.unreadCount}</span>}</div></div></div></button>)}
          {inbox.hasNextPage && <div className="p-4"><Button variant="secondary" className="w-full" disabled={inbox.isFetchingNextPage} onClick={() => inbox.fetchNextPage()}>{inbox.isFetchingNextPage ? "Loading…" : "Load more"}</Button></div>}
        </div>
      </section>

      <section aria-label="Conversation thread" className={`${activeTicket ? "flex" : "hidden lg:flex"} relative min-h-0 min-w-0 flex-1 flex-col`}>
        {!activeTicket ? <EmptyThread/> : <>
          <header className="border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
            <div className="flex min-h-11 flex-wrap items-center gap-3">
              <button className="rounded-lg p-2 hover:bg-slate-100 lg:hidden" aria-label="Back to inbox" onClick={() => { setSelectedTicket(null); setShowDetails(false); }}><ArrowLeft size={18}/></button>
              <Avatar name={activeTicket.customer.name}/>
              <div className="min-w-0 flex-1"><p className="truncate font-semibold">{activeTicket.customer.name}</p><p className="truncate text-xs text-slate-500">{activeTicket.subject}{activeTicket.assignee ? ` · ${activeTicket.assignee.name}` : " · Unassigned"}</p></div>
              {conversations.data && conversations.data.length > 1 && <Select aria-label="Choose conversation" className="max-w-44 text-xs" value={activeConversationId} onChange={(event) => chooseConversation(event.target.value)}><option value="" disabled>Choose conversation</option>{conversations.data.map((conversation, index) => <option key={conversation.id} value={conversation.id}>Conversation {conversations.data!.length - index} · {titleCase(conversation.channel)}</option>)}</Select>}
              <StatusPill value={activeTicket.status}/>
              {canReply && !activeTicket.assignee && <Button size="sm" variant="secondary" disabled={claimTicket.isPending} onClick={() => claimTicket.mutate()} aria-label="Assign ticket to me"><UserRoundPlus size={15}/><span className="hidden xl:inline">Assign to me</span></Button>}
              {canReply && <Button size="sm" variant={activeTicket.status === "resolved" ? "secondary" : "primary"} disabled={resolveTicket.isPending} onClick={() => resolveTicket.mutate()} aria-label={activeTicket.status === "resolved" ? "Reopen ticket" : "Resolve ticket"}><CheckCircle2 size={15}/><span className="hidden xl:inline">{activeTicket.status === "resolved" ? "Reopen" : "Resolve"}</span></Button>}
              <button className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 2xl:hidden" onClick={() => setShowDetails(true)} aria-label="Open ticket and customer details"><PanelRight size={15}/>Details</button>
            </div>
            {isWidgetConversation && selectedThread && <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
              <div className="min-w-0 flex-1"><p className="text-xs font-semibold text-slate-700">Reply mode</p><p className="text-[11px] text-slate-500">{selectedThread.ai_mode === "ai" ? "AI handles new messages; sensitive requests can still need review." : "AI is paused. Your team handles this thread."}</p><p className="mt-1 text-[11px] text-slate-500">Routed bot: <span className="font-medium text-slate-700">{aiAgents.data?.items.find((agent) => agent.id === selectedThread.ai_agent_id)?.name ?? "Configured AI bot"}</span>{selectedThread.ai_agent_override ? " · manually selected" : " · automatic routing"}</p></div>
              <label className="block min-w-44 text-[11px] font-semibold text-slate-600">Bot for this conversation<Select aria-label="Bot for this conversation" className="mt-1 min-h-9 w-full px-2 text-xs" value={selectedThread.ai_agent_override ? selectedThread.ai_agent_id : ""} disabled={!canReply || aiAgents.isPending || aiAgents.isError || changeConversationAgent.isPending} onChange={(event) => changeConversationAgent.mutate(event.target.value || null)}><option value="">Automatic routing</option>{aiAgents.data?.items.filter((agent) => agent.status === "active").map((agent) => <option key={agent.id} value={agent.id}>{agent.name}{agent.is_default ? " · default" : ""}</option>)}</Select></label>
              <div className="inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1" role="group" aria-label="Conversation reply mode">
                <button type="button" aria-pressed={selectedThread.ai_mode === "ai"} disabled={!canReply || changeAIMode.isPending} onClick={() => changeAIMode.mutate("ai")} className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition ${selectedThread.ai_mode === "ai" ? "bg-[var(--accent)] text-[var(--text-on-accent)] shadow-sm" : "text-slate-600 hover:bg-white"}`}><Bot size={14}/>AI mode</button>
                <button type="button" aria-pressed={selectedThread.ai_mode === "human"} disabled={!canReply || changeAIMode.isPending} onClick={() => changeAIMode.mutate("human")} className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition ${selectedThread.ai_mode === "human" ? "bg-slate-800 text-slate-50 shadow-sm" : "text-slate-600 hover:bg-white"}`}><UserRound size={14}/>Human mode</button>
              </div>
              {changeAIMode.isError && <p role="alert" className="w-full text-xs text-red-700">{changeAIMode.error instanceof Error ? changeAIMode.error.message : "Reply mode could not be changed."}</p>}
              {changeConversationAgent.isError && <p role="alert" className="w-full text-xs text-red-700">{changeConversationAgent.error instanceof Error ? changeConversationAgent.error.message : "Conversation bot could not be changed."}</p>}
            </div>}
          </header>
          {(claimTicket.isError || resolveTicket.isError) && <p role="alert" className="border-b border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700">{claimTicket.error instanceof Error ? claimTicket.error.message : resolveTicket.error instanceof Error ? resolveTicket.error.message : "Ticket update failed."}</p>}
          <div
            ref={transcriptRef}
            onDragOver={(event) => {
              if (!canReply || !activeConversationId || !Array.from(event.dataTransfer.types).includes("Files")) return;
              event.preventDefault();
              setFileDropActive(true);
            }}
            onDragLeave={(event) => {
              if (event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) return;
              setFileDropActive(false);
            }}
            onDrop={handleAttachmentDrop}
            onScroll={() => {
              const element = transcriptRef.current;
              if (!element) return;
              const distanceFromLatest = element.scrollHeight - element.scrollTop - element.clientHeight;
              followLatestMessage.current = distanceFromLatest < 120;
            }}
            className="relative min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain bg-slate-50 p-4 sm:p-6"
            aria-live="polite"
          >
            {fileDropActive && <div aria-hidden="true" className="pointer-events-none absolute inset-3 z-20 grid place-items-center rounded-2xl border-2 border-dashed border-blue-500 bg-blue-50/95 text-center text-sm font-semibold text-blue-800 shadow-lg">Drop one supported file to add it privately to this conversation</div>}
            {conversations.isPending && <p className="text-sm text-slate-500">Loading conversations…</p>}
            {conversations.isError && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"><p className="font-semibold">Could not load this ticket’s conversations</p><p className="mt-1 break-words text-xs">{formatInboxRequestError(conversations.error, "Conversation request failed.")}</p><button className="mt-2 font-semibold underline" onClick={() => conversations.refetch()}>Try again</button></div>}
            {conversations.data?.length === 0 && <div className="mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white p-6 text-center"><p className="font-semibold">No conversation yet</p><p className="mt-1 text-sm text-slate-500">Start a thread to reply to this customer from the inbox.</p>{canReply && <Button className="mt-4" disabled={startThread.isPending} onClick={() => startThread.mutate()}>{startThread.isPending ? "Starting…" : "Start conversation"}</Button>}{startThread.isError && <p role="alert" className="mt-3 text-sm text-red-700">{startThread.error instanceof Error ? startThread.error.message : "Could not start a conversation."}</p>}</div>}
            {read.isError && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700"><p>Could not update this conversation’s read status.</p><button type="button" className="mt-1 font-semibold underline" disabled={read.isPending || !activeConversationId} onClick={() => activeConversationId && read.mutate(activeConversationId)}>Try again</button></div>}
            {conversations.data && conversations.data.length > 1 && !activeConversationId && <div className="mx-auto max-w-xl rounded-2xl border border-blue-200 bg-white p-6 shadow-sm"><p className="font-semibold">Choose a conversation</p><p className="mt-1 text-sm text-slate-500">This ticket has separate conversation histories. Select one to view its messages.</p><div className="mt-4 space-y-2">{conversations.data.map((conversation, index) => <button key={conversation.id} onClick={() => chooseConversation(conversation.id)} className="flex w-full items-center justify-between rounded-xl border border-slate-200 p-3 text-left hover:border-blue-300 hover:bg-blue-50"><span><span className="block text-sm font-semibold">Conversation {conversations.data!.length - index}</span><span className="text-xs text-slate-500">{titleCase(conversation.channel)} · updated {formatDateTime(conversation.updated_at)}</span></span><span aria-hidden className="text-blue-700">→</span></button>)}</div></div>}
            {activeConversationId && messages.isPending && <div className="h-32 animate-pulse rounded-2xl bg-slate-200"/>}
            {activeConversationId && messages.isError && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"><p className="font-semibold">Could not load messages</p><p className="mt-1 break-words text-xs">{formatInboxRequestError(messages.error, "Message request failed.")}</p><button className="mt-2 font-semibold underline" onClick={() => messages.refetch()}>Try again</button></div>}
            {notes.isError && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"><p className="font-semibold">Could not load internal notes</p><p className="mt-1 break-words text-xs">{formatInboxRequestError(notes.error, "Notes request failed.")}</p><button className="mt-2 font-semibold underline" onClick={() => notes.refetch()}>Try again</button></div>}
            {activeConversationId && widgetAI.isError && <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700"><p className="font-semibold">AI status is unavailable</p><p className="mt-1 break-words text-xs">{formatInboxRequestError(widgetAI.error, "The AI status request failed.")}</p><button className="mt-2 font-semibold underline" onClick={() => widgetAI.refetch()}>Try again</button></div>}
            {[...(messages.data ?? []), ...(notes.data ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id)).map((message) => {
              const isNote = message.sender_type === "internal_note";
              const fromAgent = message.sender_type === "agent" || message.sender_type === "assistant";
              const senderName = message.sender_type === "assistant" ? "SupportPilot AI" : message.sender_name ?? titleCase(message.sender_type);
              const deliveryLabel = message.delivery_job_status === "queued" || message.delivery_job_status === "running"
                ? "Sending through integration…"
                : message.delivery_job_status === "succeeded"
                  ? message.delivery_status === "delivered" ? "Delivered" : "Sent"
                  : message.delivery_job_status === "failed" || message.delivery_status === "failed"
                    ? `Delivery failed${message.delivery_error_code ? ` · ${message.delivery_error_code}` : ""}${message.delivery_correlation_id ? ` · Ref ${message.delivery_correlation_id}` : ""}`
                    : message.delivery_job_status === "cancelled" ? "Delivery cancelled" : null;
              const deliveryFailed = message.delivery_job_status === "failed" || message.delivery_status === "failed";
              return <motion.div key={message.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }} className={`flex ${isNote || !fromAgent ? "justify-start" : "justify-end"}`}><article aria-label={isNote ? "Internal note" : message.sender_type === "assistant" ? "AI reply" : undefined} className={`max-w-[88%] rounded-2xl px-4 py-3 sm:max-w-[72%] ${isNote ? "border border-amber-200 bg-amber-50 text-amber-700" : fromAgent ? "rounded-br-md border border-blue-200 bg-blue-50 text-slate-900" : "rounded-bl-md border border-slate-200 bg-white text-slate-900"}`}><div className={`mb-1.5 flex gap-2 text-xs ${isNote ? "text-amber-700" : fromAgent ? "text-blue-700" : "text-slate-500"}`}><span className="font-semibold">{isNote ? `Internal note · ${message.sender_name ?? "Teammate"}` : senderName}</span><time>{formatDateTime(message.created_at)}</time></div><p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>{fromAgent && deliveryLabel && <div role={deliveryFailed ? "alert" : "status"} className={`mt-2 border-t pt-2 text-[11px] ${deliveryFailed ? "border-red-200 text-red-700" : "border-blue-200 text-blue-700"}`}><span>{deliveryLabel}</span>{deliveryFailed && <> · <Link href="/dashboard/settings#shopify" className="font-semibold underline underline-offset-2">Review channel settings</Link></>}</div>}</article></motion.div>;
            })}
            {isWidgetConversation && widgetAI.data && <div className={`mx-auto w-full max-w-2xl rounded-xl border p-3 text-sm ${widgetAI.data.status === "failed" ? "border-red-200 bg-red-50 text-red-700" : widgetAI.data.status === "escalated" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-blue-200 bg-blue-50 text-blue-800"}`} role={widgetAI.data.status === "processing" ? "status" : "note"}>
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-semibold">AI reply · {widgetAI.data.status.replace("_", " ")}</p><span className="rounded-full border border-current/20 px-2 py-0.5 text-[11px] font-medium">{widgetAI.data.ai_agent_name}</span></div>
              {widgetAI.data.safe_summary && <p className="mt-1 text-xs">{widgetAI.data.safe_summary}</p>}
              {widgetAI.data.status === "failed" && widgetAI.data.correlation_id && <p className="mt-1 text-xs">Support reference: <SupportTraceLink correlationId={widgetAI.data.correlation_id} /></p>}
              {widgetAI.data.status === "processing" && <p className="mt-1 text-xs">Preparing a grounded response…</p>}
              {widgetAI.data.status === "draft_ready" && widgetAI.data.draft && <><p className="mt-2 whitespace-pre-wrap">{widgetAI.data.draft}</p><div className="mt-3 flex flex-wrap gap-2"><Button type="button" size="sm" disabled={!canReply || approveWidgetDraft.isPending} onClick={() => approveWidgetDraft.mutate()}><Check size={14}/>{approveWidgetDraft.isPending ? "Sending…" : "Approve & send"}</Button><Button type="button" size="sm" variant="secondary" onClick={() => { setComposeMode("reply"); setReply(widgetAI.data?.draft ?? ""); }}>Edit draft</Button></div>{approveWidgetDraft.isError && <p role="alert" className="mt-2 text-xs text-red-700">{approveWidgetDraft.error instanceof Error ? approveWidgetDraft.error.message : "Draft could not be sent."}</p>}</>}
              {widgetAI.data.citations.length > 0 && <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"><span>Sources:</span>{widgetAI.data.citations.map((citation) => <span key={`${citation.document_id}-${citation.chunk_index}`} className="inline-flex flex-wrap items-center gap-1"><Link href={`/dashboard/knowledge/${encodeURIComponent(citation.document_id)}`} className="font-medium underline underline-offset-2">{citation.knowledge_base_name ? `${citation.knowledge_base_name} · ` : ""}{citation.document_name} · section {citation.chunk_index + 1}</Link>{citation.match_basis && <span className="rounded-full bg-white/70 px-1.5 py-0.5 text-[10px]">{citation.match_basis === "chunk_content" ? "passage" : "title"}</span>}</span>)}</div>}
            </div>}
            {activeConversationId && messages.data?.length === 0 && notes.data?.length === 0 && !notes.isPending && <p className="py-10 text-center text-sm text-slate-500">No messages or notes in this conversation.</p>}
            <div ref={transcriptEndRef} aria-hidden="true" />
          </div>
          {activeTicket && <div className="sticky bottom-0 z-10 shrink-0 border-t border-slate-200 bg-white/95 px-3 py-2 backdrop-blur sm:px-5"><ShopifyCancellationPanel ticketId={activeTicket.ticketId} compact/></div>}
          {activeConversationId && <>
            {composeMode === "reply" && (createDraft.isError || draftExecution.isError) && <p role="alert" className="border-t border-red-100 bg-red-50 px-4 py-2 text-sm text-red-700">{createDraft.error?.message ?? "Draft status could not be refreshed."}</p>}
            {composeMode === "reply" && draftExecution.data && ["queued", "running"].includes(draftExecution.data.status) && <p role="status" className="flex items-center gap-2 border-t border-blue-100 bg-blue-50 px-4 py-2 text-sm text-blue-800"><LoaderCircle size={15} className="animate-spin"/>Finding sources and preparing an unsent draft…</p>}
            {composeMode === "reply" && draftExecution.data?.status === "failed" && <div role="alert" className="border-t border-amber-100 bg-amber-50 px-4 py-2 text-sm text-amber-800"><p>The AI draft could not be completed. Your reply was not sent.</p>{draftExecution.data.correlation_id && <p className="mt-1 text-xs">Support reference: <SupportTraceLink correlationId={draftExecution.data.correlation_id} /></p>}</div>}
            {composeMode === "reply" && draftExecution.data?.status === "succeeded" && <div className="border-t border-slate-200 bg-slate-50 px-4 py-3 sm:px-5">
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-semibold text-slate-700">AI draft · review before sending</p><Button size="sm" variant="secondary" onClick={() => setReply(draftExecution.data?.draft ?? "")}>Add to reply</Button></div>
              <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-sm leading-5 text-slate-600">{draftExecution.data.draft}</p>
              {draftExecution.data.citations.length > 0 && <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-blue-700"><span>Sources:</span>{draftExecution.data.citations.map((citation) => <span key={`${citation.document_id}-${citation.chunk_index}`} className="inline-flex flex-wrap items-center gap-1"><Link href={`/dashboard/knowledge/${encodeURIComponent(citation.document_id)}`} className="font-medium underline underline-offset-2">{citation.knowledge_base_name ? `${citation.knowledge_base_name} · ` : ""}{citation.document_name} · section {citation.chunk_index + 1}</Link>{citation.match_basis && <span className="rounded-full bg-blue-50 px-1.5 py-0.5 text-[10px]">{citation.match_basis === "chunk_content" ? "passage" : "title"}</span>}</span>)}</div>}
              {draftExecution.data.citations.length === 0 && <p className="mt-2 text-xs text-amber-700">No matching knowledge sources were found. Verify the draft carefully.</p>}
            </div>}
            <form onSubmit={(event) => { event.preventDefault(); if (reply.trim()) send.mutate(); }} className={`shrink-0 border-t p-3 sm:p-4 ${composeMode === "note" ? "border-amber-200 bg-amber-50/60" : "border-slate-200 bg-white"}`}>
              <div className="mb-3 flex gap-2" role="group" aria-label="Message type"><Button type="button" size="sm" variant={composeMode === "reply" ? "primary" : "secondary"} aria-pressed={composeMode === "reply"} onClick={() => setComposeMode("reply")}>Reply</Button><Button type="button" size="sm" variant={composeMode === "note" ? "primary" : "secondary"} aria-pressed={composeMode === "note"} onClick={() => { setComposeMode("note"); setDraftExecutionId(undefined); }}>Internal note</Button></div>
              <details ref={attachmentDetailsRef} className="mb-3 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2 text-xs text-slate-600">
                <summary className="flex cursor-pointer list-none items-center gap-2 font-medium"><Paperclip size={14}/>Team files <span className="text-slate-400">({attachments.data?.length ?? 0})</span></summary>
                <p className="mt-2">Files are private to this workspace. They are not sent to the customer. Up to 20 files and 100 MB total per conversation; each file can be 10 MB.</p>
                {attachments.isPending && <p className="mt-2 text-slate-500">Loading files…</p>}
                {attachments.isError && <div className="mt-2 text-red-700"><span>Files could not be loaded. </span><button type="button" className="font-medium underline" onClick={() => attachments.refetch()}>Try again</button></div>}
                {attachments.data && attachments.data.length > 0 && <ul className="mt-2 divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">{attachments.data.map((attachment) => <li key={attachment.id} className="flex items-center gap-2 px-2.5 py-2"><span className="min-w-0 flex-1"><span className="block truncate font-medium text-slate-800">{attachment.original_filename}</span><span className="text-[11px] text-slate-500">{formatBytes(attachment.size_bytes)} · {attachment.uploaded_by_name}</span></span><Button type="button" variant="ghost" size="sm" aria-label={`Download ${attachment.original_filename}`} disabled={downloadAttachment.isPending} onClick={() => downloadAttachment.mutate({ attachmentId: attachment.id, conversationId: attachment.conversation_id })}><Download size={14}/></Button>{canReply && (attachment.uploaded_by_user_id === me.data?.id || me.data?.role === "owner" || me.data?.role === "admin") && <Button type="button" variant="ghost" size="sm" aria-label={`Remove ${attachment.original_filename}`} disabled={removeAttachment.isPending} onClick={() => removeAttachment.mutate({ attachmentId: attachment.id, conversationId: attachment.conversation_id })}><Trash2 size={14}/></Button>}</li>)}</ul>}
                {canReply && <label className="mt-2 inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"><Paperclip size={14}/>{uploadAttachment.isPending ? "Uploading…" : "Add a file"}<input type="file" className="sr-only" accept=".png,.jpg,.jpeg,.webp,.pdf,.txt,.md" disabled={!canReply || uploadAttachment.isPending} onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (!file || !activeConversationId) return; const validationError = getAttachmentValidationError(file); if (validationError) { setAttachmentValidationError(validationError); return; } setAttachmentValidationError(null); uploadAttachment.mutate({ conversationId: activeConversationId, file }); }}/></label>}
                {attachmentValidationError && <p role="alert" className="mt-2 text-red-700">{attachmentValidationError}</p>}
                {uploadAttachment.isError && uploadAttachment.variables?.conversationId === activeConversationId && <p role="alert" className="mt-2 text-red-700">{uploadAttachment.error.message}</p>}
                {removeAttachment.isError && removeAttachment.variables?.conversationId === activeConversationId && <p role="alert" className="mt-2 text-red-700">File could not be removed.</p>}
                {downloadAttachment.isError && downloadAttachment.variables?.conversationId === activeConversationId && <p role="alert" className="mt-2 text-red-700">File could not be downloaded.</p>}
              </details>
              {composeMode === "note" && <p className="mb-2 text-xs font-medium text-amber-700">Only workspace teammates can see this note. It will not be sent to the customer.</p>}
              {composeMode === "reply" && <details className="mb-3 text-xs text-slate-500"><summary className="cursor-pointer font-medium">Shopify order context (optional)</summary><label className="mt-2 block max-w-xs text-xs font-medium text-slate-600">Verified order for this draft <input aria-label="Shopify order number for AI draft" value={shopifyOrderNumber} onChange={(event) => setShopifyOrderNumber(event.target.value)} placeholder="#1001 (optional)" className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"/></label></details>}
              {composeMode === "reply" && canReply && (savedReplies.data?.length ? <div className="mb-3 max-w-sm"><label className="block text-xs font-medium text-slate-600">Insert saved reply <Select aria-label="Insert saved reply" value="" onChange={(event) => { const item = savedReplies.data?.find((entry) => entry.id === event.target.value); if (!item) return; setReply((current) => current.trim() ? `${current.trim()}\n\n${item.body}` : item.body); }} className="mt-1 min-h-9 rounded-lg text-sm"><option value="">Choose a reply…</option>{savedReplies.data.map((item) => <option key={item.id} value={item.id}>{item.title} · /{item.shortcut}</option>)}</Select></label><p className="mt-1 text-[11px] text-slate-500">Or type <kbd className="rounded border border-slate-300 bg-slate-50 px-1">/shortcut</kbd> in your reply and press Tab.</p></div> : savedReplies.isError ? <p role="status" className="mb-3 text-xs text-amber-700">Saved replies unavailable. You can still write a reply.</p> : savedReplies.isSuccess ? <p className="mb-3 text-xs text-slate-500">No saved replies yet · <Link className="font-medium text-blue-700 underline" href="/dashboard/settings#saved-replies">Create one in Settings</Link></p> : null)}
              <Textarea ref={replyInputRef} aria-label={composeMode === "note" ? "Write an internal note" : "Write a reply"} placeholder={!canReply ? "Your role has read-only access" : composeMode === "note" ? "Write a private note for your team…" : "Reply to the customer…"} value={reply} disabled={!canReply || send.isPending} onChange={(event) => setReply(event.target.value)} onKeyDown={(event) => { if (event.key === "Tab" && composeMode === "reply" && savedReplies.data?.length) { const expansion = expandSavedReplyAtCursor(event.currentTarget.value, event.currentTarget.selectionStart, savedReplies.data); if (expansion) { event.preventDefault(); setReply(expansion.value); requestAnimationFrame(() => replyInputRef.current?.setSelectionRange(expansion.cursor, expansion.cursor)); return; } } if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); if (reply.trim() && canReply && !send.isPending) send.mutate(); } }} className="min-h-20 max-h-40 resize-y rounded-xl border-slate-200 bg-slate-50/60 focus:bg-white"/>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-slate-500">{composeMode === "note" ? "Private to your workspace" : "Messages are sent as you."} <span className="ml-1 text-slate-400">· Ctrl/⌘+Enter to {composeMode === "note" ? "add note" : "send"}</span></span><div className="flex gap-2">{composeMode === "reply" && <Button type="button" variant="secondary" disabled={!canReply || createDraft.isPending || Boolean(draftExecution.data && ["queued", "running"].includes(draftExecution.data.status))} onClick={() => createDraft.mutate()}><Sparkles size={15}/>{createDraft.isPending ? "Starting…" : "Draft with AI"}</Button>}<Button type="submit" disabled={!canReply || !reply.trim() || send.isPending}>{send.isPending ? composeMode === "note" ? "Saving…" : "Sending…" : composeMode === "note" ? "Add note" : "Send reply"}{composeMode === "reply" && <Send size={15}/>}</Button></div></div>
              {send.isError && <p role="alert" className="mt-2 text-sm text-red-700">{send.error instanceof Error ? send.error.message : "Message could not be sent."}</p>}
            </form>
          </>}
        </>}
      </section>

      {activeTicket && <aside aria-label="Customer context" className="hidden w-[280px] shrink-0 border-l border-slate-200 bg-white xl:block"><CustomerContextPanel item={activeTicket} role={me.data?.role ?? "viewer"}/></aside>}
      {activeTicket && showDetails && <div role="dialog" aria-modal="true" aria-label="Ticket and customer details" className="absolute inset-0 z-30 bg-black/50 xl:hidden" onClick={() => setShowDetails(false)}><div className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-white text-slate-900 shadow-2xl" onClick={(event) => event.stopPropagation()}><header className="flex h-14 items-center justify-between border-b border-slate-200 px-4"><p className="font-semibold">Ticket details</p><button autoFocus onClick={() => setShowDetails(false)} className="rounded-lg px-3 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50">Back to conversation</button></header><div className="min-h-0 flex-1"><CustomerContextPanel item={activeTicket} role={me.data?.role ?? "viewer"}/></div></div></div>}
    </div>
  </div>;
}

function Avatar({ name }: { name: string }) { return <span className="grid size-10 shrink-0 place-items-center rounded-full bg-[var(--customer-avatar)] text-sm font-bold text-[var(--customer-avatar-foreground)]">{name.trim().slice(0, 1).toUpperCase()}</span>; }
function formatBytes(size: number) { return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`; }
function StatusPill({ value }: { value: string }) { const colors: Record<string, string> = { open: "bg-emerald-50 text-emerald-700", pending: "bg-amber-50 text-amber-700", resolved: "bg-blue-50 text-blue-700", closed: "bg-slate-100 text-slate-600" }; return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${colors[value] ?? colors.closed}`}>{value}</span>; }
function SlaPill({ sla }: { sla: NonNullable<InboxItem["firstResponseSla"]> }) {
  const presentation = {
    on_track: { label: "On track", classes: "bg-emerald-50 text-emerald-700" },
    at_risk: { label: "Due soon", classes: "bg-amber-50 text-amber-700" },
    overdue: { label: "Overdue", classes: "bg-red-50 text-red-700" },
    met: { label: "SLA met", classes: "bg-blue-50 text-blue-700" },
    breached: { label: "SLA missed", classes: "bg-red-50 text-red-700" },
  }[sla.status];
  const title = sla.responded_at
    ? `First response at ${formatDateTime(sla.responded_at)} · target ${sla.target_minutes} minutes`
    : `First response due ${formatDateTime(sla.due_at)} · target ${sla.target_minutes} minutes`;
  return <span title={title} className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${presentation.classes}`}>{presentation.label}</span>;
}
function EmptyThread() { return <div className="grid flex-1 place-items-center p-8 text-center"><div><span className="mx-auto grid size-14 place-items-center rounded-2xl bg-blue-50 text-blue-700"><Send size={22}/></span><h2 className="mt-4 text-lg font-semibold">Select a ticket</h2><p className="mt-1 max-w-xs text-sm text-slate-500">Choose a conversation from your inbox to read and reply.</p></div></div>; }
function titleCase(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function relative(value: string) { const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60_000)); if (minutes < 1) return "now"; if (minutes < 60) return `${minutes}m`; const hours = Math.floor(minutes / 60); if (hours < 24) return `${hours}h`; return `${Math.floor(hours / 24)}d`; }
