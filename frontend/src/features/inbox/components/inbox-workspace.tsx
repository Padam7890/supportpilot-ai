"use client";

import { Input } from "@/components/ui";
import { SupportTraceLink } from "@/components/support-trace-link";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import Link from "next/link";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, Check, CheckCheck, CheckCircle2, CircleAlert, Clock3, Download, Filter, Inbox, LoaderCircle, Mail, MailOpen, MessageSquare, PanelLeftClose, PanelLeftOpen, Paperclip, RefreshCw, Search, Send, Sparkles, Store, Trash2, UserRoundPlus, UserRound, type LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/input";
import { Select as SelectMenu, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { listConversations, listInternalNotes, listMessages, sendInternalNote, sendMessage, startConversation, updateConversationAIAgent, updateConversationAIMode } from "@/features/conversations/api/conversation-api";
import { sendMessageSchema } from "@/features/conversations/schemas/conversation.schema";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { aiAgentsKey, listAIAgents } from "@/features/ai/api/ai-agent-api";
import { getInbox, inboxQueryKeys, markConversationRead } from "../api/inbox-api";
import type { InboxFilters, InboxSlaStatus } from "../api/inbox-api";
import type { InboxItem } from "../types/inbox.types";
import { formatDateTime } from "@/lib/utils";
import { aiQueryKeys, createReplyDraft, getAIExecution, getWidgetAIReplyStatus } from "@/features/ai/api/ai-api";
import { assignTicketToMe, updateTicket } from "@/features/tickets/api/ticket-api";
import { ShopifyCancellationPanel } from "@/features/commerce-actions/components/shopify-cancellation-panel";
import { formatInboxRequestError } from "../utils/request-error";
import { inboxQueryRetryDelay, shouldRetryInboxQuery } from "../utils/query-retry";
import { listSavedReplies, savedRepliesQueryKey } from "@/features/saved-replies/api/saved-replies-api";
import { conversationAttachmentsKey, deleteConversationAttachment, downloadConversationAttachment, listConversationAttachments, uploadConversationAttachment } from "@/features/attachments/api/conversation-attachment-api";
import { expandSavedReplyAtCursor } from "@/features/saved-replies/utils/expand-shortcut";
import { getAttachmentValidationError } from "@/features/attachments/utils/validate-attachment";

const initialFilters: InboxFilters = { scope: "all", status: "", priority: "", channel: "", teamId: "", search: "", needsApproval: false, unreadOnly: false };
const slaStatuses: Array<{ value: InboxSlaStatus; label: string }> = [
  { value: "met", label: "Met" }, { value: "breached", label: "Breached" },
  { value: "overdue", label: "Overdue" }, { value: "at_risk", label: "At risk" },
  { value: "on_track", label: "On track" },
];
function isInboxSlaStatus(value: string | undefined): value is InboxSlaStatus {
  return slaStatuses.some((status) => status.value === value);
}

function InboxView({
  label,
  icon: Icon,
  active,
  onClick,
}: {
  label: string;
  icon: LucideIcon;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      variant="unstyled"
      aria-pressed={active}
      onClick={onClick}
      className={`flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
        active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
      }`}
    >
      <Icon size={14} className={active ? "text-primary" : "text-muted-foreground"} />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {active && <span className="size-1.5 rounded-full bg-primary" />}
    </Button>
  );
}

function Avatar({ name, compact = false }: { name: string; compact?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 place-items-center rounded-full bg-muted font-semibold text-muted-foreground ${
        compact ? "size-8 text-xs" : "size-9 text-sm"
      }`}
    >
      {name.trim().slice(0, 1).toUpperCase()}
    </span>
  );
}

function ConversationListRow({ item, selected, onSelect }: { item: InboxItem; selected: boolean; onSelect: () => void }) {
  const owner = item.assignee?.name ?? item.team?.name ?? "Unassigned";
  return (
    <Button
      variant="unstyled"
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`${item.customer.name}: ${item.subject}`}
      className={`group relative w-full justify-start items-stretch border-b border-border px-3 py-3 text-left transition-colors hover:bg-muted/50 focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-ring ${selected ? "bg-muted/70" : "bg-background"}`}
    >
      <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-0.5 ${selected ? "bg-primary" : "bg-transparent"}`} />
      <div className="flex w-full min-w-0 items-start gap-2.5">
        <Avatar name={item.customer.name} compact />
        <div className="min-w-0 flex-1">
          <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_38px_20px] items-center gap-1.5">
            <span className={`min-w-0 truncate text-[13px] ${item.unreadCount ? "font-semibold text-foreground" : "font-medium text-foreground/90"}`}>
              {item.customer.name}
            </span>
            <time className="text-right text-[10px] text-muted-foreground" dateTime={item.updatedAt} title={formatDateTime(item.updatedAt)}>
              {relative(item.updatedAt)}
            </time>
            {item.unreadCount > 0 ? <span aria-label={`${item.unreadCount} unread`} className="grid size-5 place-items-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-none text-primary-foreground">{item.unreadCount}</span> : <span aria-hidden="true" className="size-5"/>}
          </div>
          <p className="mt-1 truncate text-xs font-semibold text-foreground/90">{item.subject}</p>
          <p className={`mt-0.5 truncate text-[11px] leading-4 ${item.unreadCount ? "text-foreground/80" : "text-muted-foreground"}`}>
            {item.latestMessage?.preview ?? "No messages yet"}
          </p>
          <div className="mt-2 grid min-w-0 grid-cols-[58px_38px_minmax(0,1fr)_48px] items-center gap-1.5">
            <span className="min-w-0 overflow-hidden"><StatusPill value={item.status}/></span>
            <span className="min-w-0 truncate text-[10px] capitalize text-muted-foreground">{item.priority}</span>
            <span className="min-w-0 truncate text-[10px] text-muted-foreground" title={owner}>
              {owner}
            </span>
            <span className="flex min-w-0 justify-end">{item.firstResponseSla && <SlaPill sla={item.firstResponseSla}/>}</span>
          </div>
        </div>
      </div>
    </Button>
  );
}

function formatBytes(size: number) {
  return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusPill({ value }: { value: string }) {
  const colors: Record<string, string> = {
    open: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    pending: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
    resolved: "bg-primary/10 text-primary",
    closed: "bg-muted text-muted-foreground",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-[9px] font-semibold capitalize leading-none ${colors[value] ?? colors.closed}`}>
      {value}
    </span>
  );
}

function SlaPill({ sla }: { sla: NonNullable<InboxItem["firstResponseSla"]> }) {
  const presentation = {
    on_track: { label: "On track", classes: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" },
    at_risk: { label: "Due soon", classes: "bg-amber-500/10 text-amber-700 dark:text-amber-400" },
    overdue: { label: "Overdue", classes: "bg-destructive/10 text-destructive" },
    met: { label: "SLA met", classes: "bg-primary/10 text-primary" },
    breached: { label: "SLA missed", classes: "bg-destructive/10 text-destructive" },
  }[sla.status];
  const title = sla.responded_at
    ? `First response at ${formatDateTime(sla.responded_at)} · target ${sla.target_minutes} minutes`
    : `First response due ${formatDateTime(sla.due_at)} · target ${sla.target_minutes} minutes`;
  return (
    <span title={title} className={`rounded px-1.5 py-0.5 text-[9px] font-semibold leading-none ${presentation.classes}`}>
      {presentation.label}
    </span>
  );
}

function EmptyThread() {
  return (
    <div className="grid flex-1 place-items-center p-8 text-center">
      <div>
        <span className="mx-auto grid size-14 place-items-center rounded-lg bg-primary/5 text-primary">
          <Send size={22} />
        </span>
        <h2 className="mt-4 text-lg font-semibold">Select a ticket</h2>
        <p className="mt-1 max-w-xs text-sm text-muted-foreground">Choose a conversation from your inbox to read and reply.</p>
      </div>
    </div>
  );
}

function titleCase(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function relative(value: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60_000));
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

export function InboxWorkspace({ initialOverdueOnly = false, initialSlaStatus, initialChannel = "" }: { initialOverdueOnly?: boolean; initialSlaStatus?: string; initialChannel?: string }) {
  const client = useQueryClient();
  const [filters, setFilters] = useState<InboxFilters>(() => ({ ...initialFilters, slaStatus: isInboxSlaStatus(initialSlaStatus) ? initialSlaStatus : initialOverdueOnly ? "overdue" : undefined, channel: initialChannel }));
  const [searchDraft, setSearchDraft] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<InboxItem | null>(null);
  const [selectedConversation, setSelectedConversation] = useState("");
  const [inboxNavigationOpen, setInboxNavigationOpen] = useState(true);
  const [reply, setReply] = useState("");
  const conversationDrafts = useRef(new Map<string, { reply: string; mode: "reply" | "note"; shopifyOrderNumber: string }>());
  const lastDraftConversation = useRef("");
  const replyInputRef = useRef<HTMLTextAreaElement>(null);
  const [attachmentValidationError, setAttachmentValidationError] = useState<string | null>(null);
  const [fileDropActive, setFileDropActive] = useState(false);
  const attachmentDetailsRef = useRef<HTMLDetailsElement>(null);
  const [shopifyOrderNumber, setShopifyOrderNumber] = useState("");
  const [composeMode, setComposeMode] = useState<"reply" | "note">("reply");
  const [draftExecutionId, setDraftExecutionId] = useState<string>();
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
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
    || Boolean(filters.channel)
    || Boolean(filters.teamId)
    || Boolean(filters.search)
    || filters.needsApproval
    || filters.unreadOnly
    || Boolean(filters.slaStatus)
    || Boolean(searchDraft);
  const activeInboxFilterCount = [filters.status, filters.priority, filters.slaStatus].filter(Boolean).length;
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
  useEffect(() => {
    if (!activeConversationId) {
      lastDraftConversation.current = "";
      return;
    }
    if (lastDraftConversation.current === activeConversationId) return;
    lastDraftConversation.current = activeConversationId;
    const savedDraft = conversationDrafts.current.get(activeConversationId);
    setReply(savedDraft?.reply ?? "");
    setComposeMode(savedDraft?.mode ?? "reply");
    setShopifyOrderNumber(savedDraft?.shopifyOrderNumber ?? "");
  }, [activeConversationId]);
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
  const threadMessages = messages.data;
  const latestMessage = useMemo(() => (threadMessages ?? []).reduce<NonNullable<typeof threadMessages>[number] | null>(
    (latest, message) => !latest
      || message.created_at > latest.created_at
      || (message.created_at === latest.created_at && message.id > latest.id)
      ? message
      : latest,
    null,
  ), [threadMessages]);
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
  const latestMessageId = latestMessage?.id;
  useEffect(() => {
    const markLatestAsRead = () => {
      if (!activeConversationId || !latestMessageId || document.visibilityState !== "visible") return;
      const cursor = `${activeConversationId}:${latestMessageId}`;
      if (lastReadCursor.current === cursor) return;
      lastReadCursor.current = cursor;
      read.mutate(activeConversationId);
    };
    markLatestAsRead();
    document.addEventListener("visibilitychange", markLatestAsRead);
    return () => document.removeEventListener("visibilitychange", markLatestAsRead);
  }, [activeConversationId, latestMessageId, read]);
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
  const send = useMutation({
    mutationFn: ({ conversationId, content, mode }: { conversationId: string; content: string; mode: "reply" | "note" }) => {
      const validated = sendMessageSchema.parse({ content });
      return mode === "note" ? sendInternalNote(conversationId, validated.content) : sendMessage(conversationId, validated);
    },
    onSuccess: async (_message, variables) => {
      const savedDraft = conversationDrafts.current.get(variables.conversationId);
      if (savedDraft?.mode === variables.mode && savedDraft.reply.trim() === variables.content.trim()) {
        conversationDrafts.current.delete(variables.conversationId);
      }
      if (activeConversationId === variables.conversationId && composeMode === variables.mode && reply.trim() === variables.content.trim()) {
        setReply("");
        setDraftExecutionId(undefined);
      }
      await Promise.all([
        client.invalidateQueries({ queryKey: inboxQueryKeys.messages(variables.conversationId) }),
        client.invalidateQueries({ queryKey: ["internal-notes", variables.conversationId] }),
        client.invalidateQueries({ queryKey: ["inbox"] }),
        client.invalidateQueries({ queryKey: ["widget-ai-reply", variables.conversationId] }),
      ]);
    },
  });
  const approveWidgetDraft = useMutation({
    mutationFn: ({ conversationId, content }: { conversationId: string; content: string }) =>
      sendMessage(conversationId, sendMessageSchema.parse({ content })),
    onSuccess: async (_message, variables) => {
      const savedDraft = conversationDrafts.current.get(variables.conversationId);
      if (savedDraft?.mode === "reply" && savedDraft.reply.trim() === variables.content.trim()) {
        conversationDrafts.current.delete(variables.conversationId);
      }
      if (activeConversationId === variables.conversationId && reply.trim() === variables.content.trim()) setReply("");
      await Promise.all([
        client.invalidateQueries({ queryKey: inboxQueryKeys.messages(variables.conversationId) }),
        client.invalidateQueries({ queryKey: ["widget-ai-reply", variables.conversationId] }),
        client.invalidateQueries({ queryKey: ["inbox"] }),
      ]);
    },
  });
  const createDraft = useMutation({
    mutationFn: ({ conversationId, orderNumber }: { conversationId: string; orderNumber: string }) =>
      createReplyDraft({ conversation_id: conversationId, ...(orderNumber ? { shopify_order_number: orderNumber } : {}) }),
    onSuccess: (execution, variables) => {
      if (activeConversationId === variables.conversationId) setDraftExecutionId(execution.id);
    },
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

  function chooseConversation(id: string) {
    rememberActiveDraft();
    setSelectedConversation(id);
    setAttachmentValidationError(null);
    setFileDropActive(false);
    setDraftExecutionId(undefined);
    createDraft.reset();
  }
  function changeFilters(update: (current: InboxFilters) => InboxFilters) {
    rememberActiveDraft();
    setFilters(update);
    setSelectedTicket(null);
    setSelectedConversation("");
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
    rememberActiveDraft();
    setReply("");
    setComposeMode("reply");
    setSelectedTicket(item);
    setSelectedConversation("");
    setAttachmentValidationError(null);
    setFileDropActive(false);
    setShopifyOrderNumber("");
    setDraftExecutionId(undefined);
    createDraft.reset();
  }

  function rememberActiveDraft() {
    if (!activeConversationId) return;
    conversationDrafts.current.set(activeConversationId, {
      reply,
      mode: composeMode,
      shopifyOrderNumber,
    });
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

  return <div className="relative h-full min-h-0 bg-background text-foreground">
    <div className="relative flex h-full min-h-0 overflow-hidden bg-background">
      <aside aria-label="Inbox views" className={`hidden h-full shrink-0 flex-col border-r border-border bg-muted/25 transition-[width] duration-150 xl:flex ${inboxNavigationOpen ? "w-[220px]" : "w-0 overflow-hidden border-r-0"}`}>
        <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-3"><span className="grid size-7 place-items-center rounded-md bg-primary/10 text-primary"><Inbox size={15}/></span><span className="min-w-0 flex-1 truncate text-xs font-semibold">Inbox</span><Button variant="ghost" size="icon-sm" className="size-7" aria-label="Collapse inbox navigation" title="Collapse inbox navigation" onClick={() => setInboxNavigationOpen(false)}><PanelLeftClose size={14}/></Button></div>
        <nav className="min-h-0 flex-1 space-y-5 overflow-y-auto p-2">
          <div><p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Views</p><div className="space-y-0.5">
            <InboxView label="All conversations" icon={Inbox} active={filters.scope === "all" && !filters.status && !filters.priority && !filters.channel && !filters.teamId && !filters.search && !filters.needsApproval && !filters.unreadOnly && !filters.slaStatus && !searchDraft} onClick={() => { setSearchDraft(""); changeFilters(() => initialFilters); }}/>
            <InboxView label="Assigned to me" icon={UserRound} active={filters.scope === "mine"} onClick={() => changeFilters((value) => ({ ...value, scope: "mine", status: "", needsApproval: false, unreadOnly: false, slaStatus: undefined }))}/>
            <InboxView label="Unassigned" icon={UserRoundPlus} active={filters.scope === "unassigned"} onClick={() => changeFilters((value) => ({ ...value, scope: "unassigned", status: "", needsApproval: false, unreadOnly: false, slaStatus: undefined }))}/>
            <InboxView label="Unread" icon={MailOpen} active={filters.unreadOnly} onClick={() => changeFilters((value) => ({ ...value, scope: "all", status: "", needsApproval: false, unreadOnly: !value.unreadOnly, slaStatus: undefined }))}/>
            <InboxView label="Needs attention" icon={CircleAlert} active={filters.slaStatus === "overdue"} onClick={() => changeFilters((value) => ({ ...value, scope: "all", status: "", needsApproval: false, unreadOnly: false, slaStatus: value.slaStatus === "overdue" ? undefined : "overdue" }))}/>
            <InboxView label="Needs approval" icon={CircleAlert} active={filters.needsApproval} onClick={() => changeFilters((value) => ({ ...value, scope: "all", status: "", needsApproval: !value.needsApproval, unreadOnly: false, slaStatus: undefined }))}/>
            <InboxView label="Waiting" icon={Clock3} active={filters.status === "pending"} onClick={() => changeFilters((value) => ({ ...value, scope: "all", status: value.status === "pending" ? "" : "pending", needsApproval: false, unreadOnly: false }))}/>
            <InboxView label="Resolved" icon={CheckCheck} active={filters.status === "resolved"} onClick={() => changeFilters((value) => ({ ...value, scope: "all", status: value.status === "resolved" ? "" : "resolved", needsApproval: false, unreadOnly: false }))}/>
          </div></div>
          <div><p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Channels</p><div className="space-y-0.5">
            <InboxView label="All channels" icon={MessageSquare} active={!filters.channel} onClick={() => changeFilters((value) => ({ ...value, channel: "" }))}/>
            <InboxView label="Storefront widget" icon={Store} active={filters.channel === "shopify_widget"} onClick={() => changeFilters((value) => ({ ...value, channel: value.channel === "shopify_widget" ? "" : "shopify_widget" }))}/>
            <InboxView label="Email" icon={Mail} active={filters.channel === "email"} onClick={() => changeFilters((value) => ({ ...value, channel: value.channel === "email" ? "" : "email" }))}/>
          </div></div>
        </nav>
        <p className="border-t border-border px-3 py-2.5 text-[10px] leading-4 text-muted-foreground">Views update from the live inbox filters.</p>
      </aside>

      <section aria-label="Inbox tickets" className={`${activeTicket ? "hidden lg:flex" : "flex"} min-w-0 w-full flex-col border-r border-border bg-background lg:w-[320px] lg:shrink-0`}>
        <header className="shrink-0 border-b border-border bg-background px-3 pb-3 pt-3.5">
          <div className="mb-3 flex items-center justify-between gap-2"><div className="flex min-w-0 items-center gap-2">{!inboxNavigationOpen && <Button variant="ghost" size="icon-sm" className="hidden size-7 xl:inline-flex" aria-label="Expand inbox navigation" title="Expand inbox navigation" onClick={() => setInboxNavigationOpen(true)}><PanelLeftOpen size={14}/></Button>}<div className="min-w-0"><h1 className="truncate text-base font-semibold tracking-tight">Inbox</h1><p className="mt-0.5 text-[11px] text-muted-foreground">{rows.length}{inbox.hasNextPage ? "+" : ""} conversations</p></div></div><Button size="icon-sm" variant="ghost" aria-label="Refresh inbox" title="Refresh inbox" disabled={inbox.isFetching} onClick={() => inbox.refetch()}><RefreshCw size={14} className={inbox.isFetching ? "animate-spin" : ""}/></Button></div>
          <div className="flex min-w-0 items-center gap-2">
            <label className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-md border border-input bg-background px-2.5 transition-colors focus-within:border-ring/70"><Search size={14} className="shrink-0 text-muted-foreground"/><span className="sr-only">Search inbox</span><Input className="h-8 min-w-0 flex-1 border-0 bg-transparent px-0 text-xs shadow-none focus-visible:ring-0" placeholder="Search conversations" value={searchDraft} onChange={(e) => setSearchDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") changeFilters((value) => ({ ...value, search: searchDraft })); }}/>{searchDraft && <Button variant="unstyled" type="button" className="px-1 text-[11px] text-muted-foreground hover:text-foreground" onClick={() => { setSearchDraft(""); changeFilters((value) => ({ ...value, search: "" })); }} aria-label="Clear inbox search">×</Button>}</label>
            <Button
              type="button"
              variant={filtersOpen || activeInboxFilterCount > 0 ? "secondary" : "outline"}
              size="icon-sm"
              className="relative size-9 shrink-0"
              aria-label={filtersOpen ? "Hide inbox filters" : "Show inbox filters"}
              aria-expanded={filtersOpen}
              aria-controls="inbox-filter-controls"
              title="Filters"
              onClick={() => setFiltersOpen((open) => !open)}
            >
              <Filter size={15} />
              {activeInboxFilterCount > 0 && <span aria-label={`${activeInboxFilterCount} active filters`} className="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-primary text-[9px] font-semibold text-primary-foreground">{activeInboxFilterCount}</span>}
            </Button>
          </div>
          {filtersOpen && <div id="inbox-filter-controls" className="mt-2.5 grid grid-cols-1 gap-2 rounded-lg border border-border bg-muted/20 p-2.5 sm:grid-cols-3">
            <label className="min-w-0 space-y-1"><span className="block px-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Status</span><SelectMenu value={filters.status || null} onValueChange={(value) => changeFilters((current) => ({ ...current, status: value ?? "" }))}><SelectTrigger aria-label="Filter by status" className="h-9 w-full min-w-0 rounded-md bg-background text-xs capitalize"><SelectValue placeholder="All"/></SelectTrigger><SelectContent align="start">{["open", "pending", "resolved", "closed"].map((status) => <SelectItem key={status} value={status}>{titleCase(status)}</SelectItem>)}</SelectContent></SelectMenu></label>
            <label className="min-w-0 space-y-1"><span className="block px-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Priority</span><SelectMenu value={filters.priority || null} onValueChange={(value) => changeFilters((current) => ({ ...current, priority: value ?? "" }))}><SelectTrigger aria-label="Filter by priority" className="h-9 w-full min-w-0 rounded-md bg-background text-xs capitalize"><SelectValue placeholder="All"/></SelectTrigger><SelectContent align="start">{["low", "normal", "high", "urgent"].map((priority) => <SelectItem key={priority} value={priority}>{titleCase(priority)}</SelectItem>)}</SelectContent></SelectMenu></label>
            <label className="min-w-0 space-y-1"><span className="block px-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">SLA</span><SelectMenu value={filters.slaStatus ?? null} onValueChange={(value) => changeFilters((current) => ({ ...current, slaStatus: value && isInboxSlaStatus(value) ? value : undefined }))}><SelectTrigger aria-label="Filter by SLA" className="h-9 w-full min-w-0 rounded-md bg-background text-xs capitalize"><SelectValue placeholder="All"/></SelectTrigger><SelectContent align="start">{slaStatuses.map(({ value, label }) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></SelectMenu></label>
          </div>}
          {hasActiveFilters && <Button variant="unstyled" type="button" onClick={clearFilters} className="mt-2 rounded px-1 text-[11px] font-medium text-primary hover:underline">Clear filters</Button>}
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">
          {inbox.isPending && <div className="divide-y divide-border px-3">{[1,2,3,4,5].map((i) => <div key={i} className="space-y-2 py-4"><div className="h-3 w-2/3 animate-pulse rounded bg-muted"/><div className="h-3 w-full animate-pulse rounded bg-muted/70"/><div className="h-3 w-1/2 animate-pulse rounded bg-muted/70"/></div>)}</div>}
          {inbox.isError && <div role="alert" className="m-3 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"><p className="font-semibold">Could not load the inbox</p><p className="mt-1 break-words text-xs">{formatInboxRequestError(inbox.error, "The inbox request failed.")}</p><Button variant="unstyled" className="mt-2 font-semibold underline underline-offset-2" onClick={() => inbox.refetch()}>Try again</Button></div>}
          {!inbox.isPending && !inbox.isError && rows.length === 0 && <div className="px-5 py-12 text-center"><span className="mx-auto grid size-9 place-items-center rounded-md bg-muted text-muted-foreground"><Inbox size={17}/></span><p className="mt-3 text-sm font-semibold">No conversations found</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Change a filter or clear your search to see more conversations.</p></div>}
          {rows.map((item) => <ConversationListRow key={item.ticketId} item={item} selected={activeTicket?.ticketId === item.ticketId} onSelect={() => selectTicket(item)}/>)}
          {inbox.hasNextPage && <div className="p-4"><Button variant="secondary" className="w-full" disabled={inbox.isFetchingNextPage} onClick={() => inbox.fetchNextPage()}>{inbox.isFetchingNextPage ? "Loading…" : "Load more"}</Button></div>}
        </div>
      </section>

      <section aria-label="Conversation thread" className={`${activeTicket ? "flex" : "hidden lg:flex"} relative min-h-0 min-w-0 flex-1 flex-col`}>
        {!activeTicket ? <EmptyThread/> : <>
          <header className="border-b border-border bg-background px-4 py-3 sm:px-6">
            <div className="flex min-h-11 flex-wrap items-center gap-3">
              <Button variant="unstyled" className="rounded-lg p-2 hover:bg-muted lg:hidden" aria-label="Back to inbox" onClick={() => setSelectedTicket(null)}><ArrowLeft size={18}/></Button>
              <Avatar name={activeTicket.customer.name}/>
              <div className="min-w-0 flex-1"><p className="truncate font-semibold">{activeTicket.customer.name}</p><p className="truncate text-xs text-muted-foreground">{activeTicket.assignee ? activeTicket.assignee.name : "Unassigned"}</p></div>
              {conversations.data && conversations.data.length > 1 && <Select aria-label="Choose conversation" className="max-w-44 text-xs" value={activeConversationId} onChange={(event) => chooseConversation(event.target.value)}><option value="" disabled>Choose conversation</option>{conversations.data.map((conversation, index) => <option key={conversation.id} value={conversation.id}>Conversation {conversations.data!.length - index} · {titleCase(conversation.channel)}</option>)}</Select>}
              <StatusPill value={activeTicket.status}/>
              {canReply && !activeTicket.assignee && <Button size="sm" variant="secondary" disabled={claimTicket.isPending} onClick={() => claimTicket.mutate()} aria-label="Assign ticket to me"><UserRoundPlus size={15}/><span className="hidden xl:inline">Assign to me</span></Button>}
              {canReply && <Button size="sm" variant={activeTicket.status === "resolved" ? "secondary" : "primary"} disabled={resolveTicket.isPending} onClick={() => resolveTicket.mutate()} aria-label={activeTicket.status === "resolved" ? "Reopen ticket" : "Resolve ticket"}><CheckCircle2 size={15}/><span className="hidden xl:inline">{activeTicket.status === "resolved" ? "Reopen" : "Resolve"}</span></Button>}
            </div>
            {isWidgetConversation && selectedThread && <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border/60 pt-3">
              <div className="inline-flex shrink-0 items-center"><SelectMenu value={selectedThread.ai_agent_override ? selectedThread.ai_agent_id : "__automatic__"} onValueChange={(value) => changeConversationAgent.mutate(value && value !== "__automatic__" ? value : null)}><SelectTrigger aria-label="Choose AI assistant" title="Choose the AI assistant for this conversation" disabled={!canReply || aiAgents.isPending || aiAgents.isError || changeConversationAgent.isPending} className="h-8 w-44 min-w-0 border-0 bg-muted/40 px-2 text-xs shadow-none hover:bg-muted/70 focus-visible:ring-1 focus-visible:ring-ring/40"><Bot size={13} className="shrink-0 text-muted-foreground"/><SelectValue>{selectedThread.ai_agent_override ? aiAgents.data?.items.find((agent) => agent.id === selectedThread.ai_agent_id)?.name ?? "Selected assistant" : "Automatic"}</SelectValue></SelectTrigger><SelectContent align="end" className="min-w-52"><SelectItem value="__automatic__">Automatic</SelectItem>{aiAgents.data?.items.filter((agent) => agent.status === "active").map((agent) => <SelectItem key={agent.id} value={agent.id}>{agent.name}{agent.is_default ? " · default" : ""}</SelectItem>)}</SelectContent></SelectMenu></div>
              <div className="inline-flex rounded-md border border-border bg-muted/30 p-1" role="group" aria-label="Conversation reply mode">
                <Button variant="unstyled" type="button" aria-pressed={selectedThread.ai_mode === "ai"} disabled={!canReply || changeAIMode.isPending} onClick={() => changeAIMode.mutate("ai")} className={`inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-xs font-semibold transition ${selectedThread.ai_mode === "ai" ? "bg-primary text-primary-foreground shadow-sm hover:bg-primary-hover hover:text-primary-foreground" : "text-muted-foreground hover:bg-background hover:text-foreground"}`}><Bot size={14}/>AI mode</Button>
                <Button variant="unstyled" type="button" aria-pressed={selectedThread.ai_mode === "human"} disabled={!canReply || changeAIMode.isPending} onClick={() => changeAIMode.mutate("human")} className={`inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-xs font-semibold transition ${selectedThread.ai_mode === "human" ? "bg-secondary text-secondary-foreground shadow-sm ring-1 ring-border hover:bg-secondary hover:text-secondary-foreground" : "text-muted-foreground hover:bg-background hover:text-foreground"}`}><UserRound size={14}/>Human mode</Button>
              </div>
              {changeAIMode.isError && <p role="alert" className="w-full text-xs text-destructive">{changeAIMode.error instanceof Error ? changeAIMode.error.message : "Reply mode could not be changed."}</p>}
              {changeConversationAgent.isError && <p role="alert" className="w-full text-xs text-destructive">{changeConversationAgent.error instanceof Error ? changeConversationAgent.error.message : "Conversation bot could not be changed."}</p>}
            </div>}
          </header>
          {(claimTicket.isError || resolveTicket.isError) && <p role="alert" className="border-b border-destructive/20 bg-destructive/10 px-4 py-2 text-xs text-destructive">{claimTicket.error instanceof Error ? claimTicket.error.message : resolveTicket.error instanceof Error ? resolveTicket.error.message : "Ticket update failed."}</p>}
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
            className="relative min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain bg-muted/30 p-4 sm:p-6"
            aria-live="polite"
          >
            {fileDropActive && <div aria-hidden="true" className="pointer-events-none absolute inset-3 z-20 grid place-items-center rounded-lg border-2 border-dashed border-ring bg-background/95 text-center text-sm font-semibold text-primary shadow-lg">Drop one supported file to add it privately to this conversation</div>}
            {conversations.isPending && <p className="text-sm text-muted-foreground">Loading conversations…</p>}
            {conversations.isError && <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"><p className="font-semibold">Could not load this ticket’s conversations</p><p className="mt-1 break-words text-xs">{formatInboxRequestError(conversations.error, "Conversation request failed.")}</p><Button variant="unstyled" className="mt-2 font-semibold underline" onClick={() => conversations.refetch()}>Try again</Button></div>}
            {conversations.data?.length === 0 && <div className="mx-auto max-w-xl rounded-lg border border-border bg-background p-6 text-center"><p className="font-semibold">No conversation yet</p><p className="mt-1 text-sm text-muted-foreground">Start a thread to reply to this customer from the inbox.</p>{canReply && <Button className="mt-4" disabled={startThread.isPending} onClick={() => startThread.mutate()}>{startThread.isPending ? "Starting…" : "Start conversation"}</Button>}{startThread.isError && <p role="alert" className="mt-3 text-sm text-destructive">{startThread.error instanceof Error ? startThread.error.message : "Could not start a conversation."}</p>}</div>}
            {read.isError && <div role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive"><p>Could not update this conversation’s read status.</p><Button variant="unstyled" type="button" className="mt-1 font-semibold underline" disabled={read.isPending || !activeConversationId} onClick={() => activeConversationId && read.mutate(activeConversationId)}>Try again</Button></div>}
            {conversations.data && conversations.data.length > 1 && !activeConversationId && <div className="mx-auto max-w-xl rounded-lg border border-primary/20 bg-background p-6 shadow-sm"><p className="font-semibold">Choose a conversation</p><p className="mt-1 text-sm text-muted-foreground">This ticket has separate conversation histories. Select one to view its messages.</p><div className="mt-4 space-y-2">{conversations.data.map((conversation, index) => <Button variant="unstyled" key={conversation.id} onClick={() => chooseConversation(conversation.id)} className="flex w-full items-center justify-between rounded-md border border-border p-3 text-left hover:border-primary/30 hover:bg-primary/5"><span><span className="block text-sm font-semibold">Conversation {conversations.data!.length - index}</span><span className="text-xs text-muted-foreground">{titleCase(conversation.channel)} · updated {formatDateTime(conversation.updated_at)}</span></span><span aria-hidden className="text-primary">→</span></Button>)}</div></div>}
            {activeConversationId && messages.isPending && <div className="h-32 animate-pulse rounded-lg bg-muted"/>}
            {activeConversationId && messages.isError && <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"><p className="font-semibold">Could not load messages</p><p className="mt-1 break-words text-xs">{formatInboxRequestError(messages.error, "Message request failed.")}</p><Button variant="unstyled" className="mt-2 font-semibold underline" onClick={() => messages.refetch()}>Try again</Button></div>}
            {notes.isError && <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"><p className="font-semibold">Could not load internal notes</p><p className="mt-1 break-words text-xs">{formatInboxRequestError(notes.error, "Notes request failed.")}</p><Button variant="unstyled" className="mt-2 font-semibold underline" onClick={() => notes.refetch()}>Try again</Button></div>}
            {activeConversationId && widgetAI.isError && <div role="alert" className="rounded-md border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-300"><p className="font-semibold">AI status is unavailable</p><p className="mt-1 break-words text-xs">{formatInboxRequestError(widgetAI.error, "The AI status request failed.")}</p><Button variant="unstyled" className="mt-2 font-semibold underline" onClick={() => widgetAI.refetch()}>Try again</Button></div>}
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
              return <motion.div key={message.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }} className={`flex ${isNote || !fromAgent ? "justify-start" : "justify-end"}`}><article aria-label={isNote ? "Internal note" : message.sender_type === "assistant" ? "AI reply" : undefined} className={`max-w-[88%] rounded-lg px-4 py-3 sm:max-w-[72%] ${isNote ? "border border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300" : fromAgent ? "rounded-br-md border border-primary/20 bg-primary/5 text-foreground" : "rounded-bl-md border border-border bg-background text-foreground"}`}><div className={`mb-1.5 flex gap-2 text-xs ${isNote ? "text-amber-700 dark:text-amber-300" : fromAgent ? "text-primary" : "text-muted-foreground"}`}><span className="font-semibold">{isNote ? `Internal note · ${message.sender_name ?? "Teammate"}` : senderName}</span><time>{formatDateTime(message.created_at)}</time></div><p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>{fromAgent && deliveryLabel && <div role={deliveryFailed ? "alert" : "status"} className={`mt-2 border-t pt-2 text-[11px] ${deliveryFailed ? "border-destructive/30 text-destructive" : "border-primary/20 text-primary"}`}><span>{deliveryLabel}</span>{deliveryFailed && <> · <Link href="/dashboard/settings#shopify" className="font-semibold underline underline-offset-2">Review channel settings</Link></>}</div>}</article></motion.div>;
            })}
            {isWidgetConversation && widgetAI.data && <div className={`mx-auto w-full max-w-2xl rounded-md border p-3 text-sm ${widgetAI.data.status === "failed" ? "border-destructive/30 bg-destructive/10 text-destructive" : widgetAI.data.status === "escalated" ? "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300" : "border-primary/20 bg-primary/5 text-primary"}`} role={widgetAI.data.status === "processing" ? "status" : "note"}>
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-semibold">AI reply · {widgetAI.data.status.replace("_", " ")}</p><span className="rounded-full border border-current/20 px-2 py-0.5 text-[11px] font-medium">{widgetAI.data.ai_agent_name}</span></div>
              {widgetAI.data.safe_summary && <p className="mt-1 text-xs">{widgetAI.data.safe_summary}</p>}
              {widgetAI.data.status === "failed" && widgetAI.data.correlation_id && <p className="mt-1 text-xs">Support reference: <SupportTraceLink correlationId={widgetAI.data.correlation_id} /></p>}
              {widgetAI.data.status === "processing" && <p className="mt-1 text-xs">Preparing a grounded response…</p>}
              {widgetAI.data.status === "draft_ready" && widgetAI.data.draft && <><p className="mt-2 whitespace-pre-wrap">{widgetAI.data.draft}</p><div className="mt-3 flex flex-wrap gap-2"><Button type="button" size="sm" disabled={!canReply || approveWidgetDraft.isPending} onClick={() => approveWidgetDraft.mutate({ conversationId: activeConversationId, content: widgetAI.data?.draft ?? "" })}><Check size={14}/>{approveWidgetDraft.isPending ? "Sending…" : "Approve & send"}</Button><Button type="button" size="sm" variant="secondary" onClick={() => { setComposeMode("reply"); setReply(widgetAI.data?.draft ?? ""); }}>Edit draft</Button></div>{approveWidgetDraft.isError && approveWidgetDraft.variables?.conversationId === activeConversationId && <p role="alert" className="mt-2 text-xs text-destructive">{approveWidgetDraft.error instanceof Error ? approveWidgetDraft.error.message : "Draft could not be sent."}</p>}</>}
              {widgetAI.data.citations.length > 0 && <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"><span>Sources:</span>{widgetAI.data.citations.map((citation) => <span key={`${citation.document_id}-${citation.chunk_index}`} className="inline-flex flex-wrap items-center gap-1"><Link href={`/dashboard/knowledge/${encodeURIComponent(citation.document_id)}`} className="font-medium underline underline-offset-2">{citation.knowledge_base_name ? `${citation.knowledge_base_name} · ` : ""}{citation.document_name} · section {citation.chunk_index + 1}</Link>{citation.match_basis && <span className="rounded-full bg-background/70 px-1.5 py-0.5 text-[10px]">{citation.match_basis === "chunk_content" ? "passage" : "title"}</span>}</span>)}</div>}
            </div>}
            {activeConversationId && messages.data?.length === 0 && notes.data?.length === 0 && !notes.isPending && <p className="py-10 text-center text-sm text-muted-foreground">No messages or notes in this conversation.</p>}
            <div ref={transcriptEndRef} aria-hidden="true" />
          </div>
          {activeTicket && <div className="sticky bottom-0 z-10 shrink-0 border-t border-border bg-background/95 px-3 py-2 backdrop-blur sm:px-5"><ShopifyCancellationPanel ticketId={activeTicket.ticketId} compact/></div>}
          {activeConversationId && <>
            {composeMode === "reply" && ((createDraft.isError && createDraft.variables?.conversationId === activeConversationId) || draftExecution.isError) && <p role="alert" className="border-t border-destructive/20 bg-destructive/10 px-4 py-2 text-sm text-destructive">{createDraft.error?.message ?? "Draft status could not be refreshed."}</p>}
            {composeMode === "reply" && draftExecution.data && ["queued", "running"].includes(draftExecution.data.status) && <p role="status" className="flex items-center gap-2 border-t border-primary/20 bg-primary/5 px-4 py-2 text-sm text-primary"><LoaderCircle size={15} className="animate-spin"/>Finding sources and preparing an unsent draft…</p>}
            {composeMode === "reply" && draftExecution.data?.status === "failed" && <div role="alert" className="border-t border-amber-500/20 bg-amber-500/10 px-4 py-2 text-sm text-amber-800 dark:text-amber-300"><p>The AI draft could not be completed. Your reply was not sent.</p>{draftExecution.data.correlation_id && <p className="mt-1 text-xs">Support reference: <SupportTraceLink correlationId={draftExecution.data.correlation_id} /></p>}</div>}
            {composeMode === "reply" && draftExecution.data?.status === "succeeded" && <div className="border-t border-border bg-muted/30 px-4 py-3 sm:px-5">
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-semibold text-foreground/90">AI draft · review before sending</p><Button size="sm" variant="secondary" onClick={() => setReply(draftExecution.data?.draft ?? "")}>Add to reply</Button></div>
              <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-sm leading-5 text-muted-foreground">{draftExecution.data.draft}</p>
              {draftExecution.data.citations.length > 0 && <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-primary"><span>Sources:</span>{draftExecution.data.citations.map((citation) => <span key={`${citation.document_id}-${citation.chunk_index}`} className="inline-flex flex-wrap items-center gap-1"><Link href={`/dashboard/knowledge/${encodeURIComponent(citation.document_id)}`} className="font-medium underline underline-offset-2">{citation.knowledge_base_name ? `${citation.knowledge_base_name} · ` : ""}{citation.document_name} · section {citation.chunk_index + 1}</Link>{citation.match_basis && <span className="rounded-full bg-primary/5 px-1.5 py-0.5 text-[10px]">{citation.match_basis === "chunk_content" ? "passage" : "title"}</span>}</span>)}</div>}
              {draftExecution.data.citations.length === 0 && <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">No matching knowledge sources were found. Verify the draft carefully.</p>}
            </div>}
            <form onSubmit={(event) => { event.preventDefault(); if (reply.trim() && activeConversationId) send.mutate({ conversationId: activeConversationId, content: reply, mode: composeMode }); }} className={`shrink-0 border-t p-3 sm:p-4 ${composeMode === "note" ? "border-amber-500/30 bg-amber-500/10" : "border-border bg-background"}`}>
              <div className="mb-3 flex gap-2" role="group" aria-label="Message type"><Button type="button" size="sm" variant={composeMode === "reply" ? "primary" : "secondary"} aria-pressed={composeMode === "reply"} onClick={() => setComposeMode("reply")}>Reply</Button><Button type="button" size="sm" variant={composeMode === "note" ? "primary" : "secondary"} aria-pressed={composeMode === "note"} onClick={() => { setComposeMode("note"); setDraftExecutionId(undefined); }}>Internal note</Button></div>
              <details ref={attachmentDetailsRef} className="mb-3 rounded-lg border border-border bg-muted/70 px-3 py-2 text-xs text-muted-foreground">
                <summary className="flex cursor-pointer list-none items-center gap-2 font-medium"><Paperclip size={14}/>Team files <span className="text-muted-foreground/70">({attachments.data?.length ?? 0})</span></summary>
                <p className="mt-2">Files are private to this workspace. They are not sent to the customer. Up to 20 files and 100 MB total per conversation; each file can be 10 MB.</p>
                {attachments.isPending && <p className="mt-2 text-muted-foreground">Loading files…</p>}
                {attachments.isError && <div className="mt-2 text-destructive"><span>Files could not be loaded. </span><Button variant="unstyled" type="button" className="font-medium underline" onClick={() => attachments.refetch()}>Try again</Button></div>}
                {attachments.data && attachments.data.length > 0 && <ul className="mt-2 divide-y divide-border rounded-lg border border-border bg-background">{attachments.data.map((attachment) => <li key={attachment.id} className="flex items-center gap-2 px-2.5 py-2"><span className="min-w-0 flex-1"><span className="block truncate font-medium text-foreground">{attachment.original_filename}</span><span className="text-[11px] text-muted-foreground">{formatBytes(attachment.size_bytes)} · {attachment.uploaded_by_name}</span></span><Button type="button" variant="ghost" size="sm" aria-label={`Download ${attachment.original_filename}`} disabled={downloadAttachment.isPending} onClick={() => downloadAttachment.mutate({ attachmentId: attachment.id, conversationId: attachment.conversation_id })}><Download size={14}/></Button>{canReply && (attachment.uploaded_by_user_id === me.data?.id || me.data?.role === "owner" || me.data?.role === "admin") && <Button type="button" variant="ghost" size="sm" aria-label={`Remove ${attachment.original_filename}`} disabled={removeAttachment.isPending} onClick={() => removeAttachment.mutate({ attachmentId: attachment.id, conversationId: attachment.conversation_id })}><Trash2 size={14}/></Button>}</li>)}</ul>}
                {canReply && <label className="mt-2 inline-flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs font-semibold text-foreground/90 hover:bg-muted/60"><Paperclip size={14}/>{uploadAttachment.isPending ? "Uploading…" : "Add a file"}<input type="file" className="sr-only" accept=".png,.jpg,.jpeg,.webp,.pdf,.txt,.md" disabled={!canReply || uploadAttachment.isPending} onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (!file || !activeConversationId) return; const validationError = getAttachmentValidationError(file); if (validationError) { setAttachmentValidationError(validationError); return; } setAttachmentValidationError(null); uploadAttachment.mutate({ conversationId: activeConversationId, file }); }}/></label>}
                {attachmentValidationError && <p role="alert" className="mt-2 text-destructive">{attachmentValidationError}</p>}
                {uploadAttachment.isError && uploadAttachment.variables?.conversationId === activeConversationId && <p role="alert" className="mt-2 text-destructive">{uploadAttachment.error.message}</p>}
                {removeAttachment.isError && removeAttachment.variables?.conversationId === activeConversationId && <p role="alert" className="mt-2 text-destructive">File could not be removed.</p>}
                {downloadAttachment.isError && downloadAttachment.variables?.conversationId === activeConversationId && <p role="alert" className="mt-2 text-destructive">File could not be downloaded.</p>}
              </details>
              {composeMode === "note" && <p className="mb-2 text-xs font-medium text-amber-700 dark:text-amber-300">Only workspace teammates can see this note. It will not be sent to the customer.</p>}
              {composeMode === "reply" && <details className="mb-3 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium">Shopify order context (optional)</summary><label className="mt-2 block max-w-xs text-xs font-medium text-muted-foreground">Verified order for this draft <Input aria-label="Shopify order number for AI draft" value={shopifyOrderNumber} onChange={(event) => setShopifyOrderNumber(event.target.value)} placeholder="#1001 (optional)" className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm text-foreground outline-none focus:border-ring/70 focus:ring-2 focus:ring-ring/20"/></label></details>}
              {composeMode === "reply" && canReply && (savedReplies.data?.length ? <div className="mb-3 max-w-sm"><label className="block text-xs font-medium text-muted-foreground">Insert saved reply <Select aria-label="Insert saved reply" value="" onChange={(event) => { const item = savedReplies.data?.find((entry) => entry.id === event.target.value); if (!item) return; setReply((current) => current.trim() ? `${current.trim()}\n\n${item.body}` : item.body); }} className="mt-1 min-h-9 rounded-lg text-sm"><option value="">Choose a reply…</option>{savedReplies.data.map((item) => <option key={item.id} value={item.id}>{item.title} · /{item.shortcut}</option>)}</Select></label><p className="mt-1 text-[11px] text-muted-foreground">Or type <kbd className="rounded border border-border bg-muted/30 px-1">/shortcut</kbd> in your reply and press Tab.</p></div> : savedReplies.isError ? <p role="status" className="mb-3 text-xs text-amber-700 dark:text-amber-300">Saved replies unavailable. You can still write a reply.</p> : savedReplies.isSuccess ? <p className="mb-3 text-xs text-muted-foreground">No saved replies yet · <Link className="font-medium text-primary underline" href="/dashboard/settings#saved-replies">Create one in Settings</Link></p> : null)}
              <Textarea ref={replyInputRef} aria-label={composeMode === "note" ? "Write an internal note" : "Write a reply"} placeholder={!canReply ? "Your role has read-only access" : composeMode === "note" ? "Write a private note for your team…" : "Reply to the customer…"} value={reply} disabled={!canReply || send.isPending} onChange={(event) => setReply(event.target.value)} onKeyDown={(event) => { if (event.key === "Tab" && composeMode === "reply" && savedReplies.data?.length) { const expansion = expandSavedReplyAtCursor(event.currentTarget.value, event.currentTarget.selectionStart, savedReplies.data); if (expansion) { event.preventDefault(); setReply(expansion.value); requestAnimationFrame(() => replyInputRef.current?.setSelectionRange(expansion.cursor, expansion.cursor)); return; } } if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); if (reply.trim() && canReply && !send.isPending && activeConversationId) send.mutate({ conversationId: activeConversationId, content: reply, mode: composeMode }); } }} className="min-h-20 max-h-40 resize-y rounded-md border-border bg-muted/30 focus:bg-background"/>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-muted-foreground">{composeMode === "note" ? "Private to your workspace" : "Messages are sent as you."} <span className="ml-1 text-muted-foreground/70">· Ctrl/⌘+Enter to {composeMode === "note" ? "add note" : "send"}</span></span><div className="flex gap-2">{composeMode === "reply" && <Button type="button" variant="secondary" disabled={!canReply || createDraft.isPending || Boolean(draftExecution.data && ["queued", "running"].includes(draftExecution.data.status))} onClick={() => activeConversationId && createDraft.mutate({ conversationId: activeConversationId, orderNumber: shopifyOrderNumber.trim() })}><Sparkles size={15}/>{createDraft.isPending ? "Starting…" : "Draft with AI"}</Button>}<Button type="submit" disabled={!canReply || !reply.trim() || send.isPending}>{send.isPending ? composeMode === "note" ? "Saving…" : "Sending…" : composeMode === "note" ? "Add note" : "Send reply"}{composeMode === "reply" && <Send size={15}/>}</Button></div></div>
              {send.isError && send.variables?.conversationId === activeConversationId && <p role="alert" className="mt-2 text-sm text-destructive">{send.error instanceof Error ? send.error.message : "Message could not be sent."}</p>}
            </form>
          </>}
        </>}
      </section>

    </div>
  </div>;
}
