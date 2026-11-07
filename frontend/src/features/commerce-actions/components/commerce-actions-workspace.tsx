"use client";

import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, BadgeCheck, Ban, CircleAlert, ClipboardCheck, Clock3, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import { SupportTraceLink } from "@/components/support-trace-link";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { getCurrentUser, currentUserQueryKey } from "@/features/auth/api/auth-api";
import { listTickets } from "@/features/tickets/api/ticket-api";
import type { Ticket } from "@/features/tickets/types/ticket.types";
import { ApiError } from "@/lib/api/errors";
import {
  approveCommerceAction,
  cancelCommerceAction,
  commerceActionKeys,
  createCommerceAction,
  getCommerceActionAudit,
  listCommerceActions,
  rejectCommerceAction,
  type CommerceAction,
} from "../api/commerce-actions-api";

const PAGE_SIZE = 25;

export function CommerceActionsWorkspace() {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string>();
  const isReviewer = me.data?.role === "owner" || me.data?.role === "admin";
  const canRequest = me.data?.role === "owner" || me.data?.role === "admin" || me.data?.role === "agent";
  const actions = useQuery({
    queryKey: commerceActionKeys.list(statusFilter || undefined, offset),
    queryFn: () => listCommerceActions(statusFilter || undefined, offset),
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 10_000 : false,
    refetchIntervalInBackground: false,
  });
  const tickets = useQuery({
    queryKey: ["tickets", "commerce-action-options"],
    queryFn: () => listTickets("limit=100&offset=0"),
    enabled: canRequest,
  });
  const selected = actions.data?.items.find((item) => item.id === selectedId);
  const audit = useQuery({
    queryKey: commerceActionKeys.audit(selectedId ?? ""),
    queryFn: () => getCommerceActionAudit(selectedId!),
    enabled: Boolean(selectedId),
  });
  const invalidateActions = async (actionId?: string) => {
    await queryClient.invalidateQueries({ queryKey: ["commerce-actions"] });
    if (actionId) await queryClient.invalidateQueries({ queryKey: commerceActionKeys.audit(actionId) });
  };
  const approve = useMutation({ mutationFn: approveCommerceAction, onSuccess: (action) => invalidateActions(action.id) });
  const reject = useMutation({ mutationFn: rejectCommerceAction, onSuccess: (action) => invalidateActions(action.id) });
  const cancel = useMutation({ mutationFn: cancelCommerceAction, onSuccess: (action) => invalidateActions(action.id) });
  const busyDecision = approve.isPending || reject.isPending || cancel.isPending;
  const decisionError = approve.error ?? reject.error ?? cancel.error;

  return <section aria-labelledby="commerce-actions-heading" className="space-y-5 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div><p className="text-xs font-bold uppercase tracking-[.15em] text-blue-700">Human-reviewed order operations</p><h2 id="commerce-actions-heading" className="mt-1 text-xl font-bold">Refund and cancellation requests</h2><p className="mt-1 max-w-2xl text-sm text-slate-500">Requests are matched to a ticket’s CRM customer, reviewed by an Owner/Admin, and simulated by the mock commerce worker. Shopify orders are never changed.</p></div>
      <label className="space-y-1 text-xs font-semibold text-slate-600"><span>Approval status</span><Select aria-label="Filter commerce actions by approval status" value={statusFilter} onChange={(event) => { setOffset(0); setStatusFilter(event.target.value); }} className="min-w-40"><option value="">All requests</option><option value="pending">Pending review</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="expired">Expired</option><option value="cancelled">Cancelled</option></Select></label>
    </header>

    {canRequest && <RequestActionForm tickets={tickets.data?.items ?? []} ticketsLoading={tickets.isPending} onSuccess={async (action) => { setSelectedId(action.id); setStatusFilter(""); setOffset(0); await invalidateActions(action.id); }}/ >}

    {actions.isPending && <div className="h-32 animate-pulse rounded-2xl bg-slate-100" role="status" aria-label="Loading requests"/>}
    {actions.isError && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{actions.error instanceof ApiError ? actions.error.message : "Commerce action requests could not be loaded."}</p>}
    {actions.data && actions.data.items.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center"><ClipboardCheck className="mx-auto text-slate-400"/><h3 className="mt-3 font-semibold">No requests in this view</h3><p className="mt-1 text-sm text-slate-500">New ticket-linked refund or cancellation requests will appear here.</p></div>}

    {actions.data && actions.data.items.length > 0 && <>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(280px,.7fr)]">
        <ul aria-label="Commerce action requests" className="space-y-2">
          {actions.data.items.map((item) => <li key={item.id}>
            <button type="button" aria-pressed={selectedId === item.id} onClick={() => setSelectedId(item.id)} className={`w-full rounded-2xl border p-4 text-left transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-100 ${selectedId === item.id ? "border-blue-400 bg-blue-50/60" : "border-slate-200 hover:border-blue-200 hover:bg-slate-50"}`}>
              <span className="flex flex-wrap items-center justify-between gap-2"><span className="font-semibold capitalize text-slate-900">{item.action_type} · {item.order_number}</span><span className="flex flex-wrap gap-1.5"><StatusBadge value={item.approval_status}/><StatusBadge value={item.execution_status}/></span></span>
              <span className="mt-2 block text-sm text-slate-600">{item.action_type === "refund" ? `${item.refund_amount} ${item.currency} of ${item.order_total} ${item.currency}` : `${item.order_total} ${item.currency} order`} · requested by {item.requested_by_name}</span>
              <span className="mt-1 block text-xs text-slate-500">{new Date(item.created_at).toLocaleString()} · {item.reason}</span>
            </button>
          </li>)}
        </ul>
        {selected && <ActionDetails action={selected} audit={audit.data?.items ?? []} auditLoading={audit.isPending} isReviewer={isReviewer} currentUserId={me.data?.id} busy={busyDecision} error={decisionError} onApprove={() => approve.mutate(selected.id)} onReject={() => reject.mutate(selected.id)} onCancel={() => cancel.mutate(selected.id)}/>}
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4 text-sm text-slate-500"><span>Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, actions.data.total)} of {actions.data.total}</span><div className="flex gap-2"><Button variant="secondary" size="sm" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0}><ArrowLeft size={14}/>Previous</Button><Button variant="secondary" size="sm" onClick={() => setOffset(offset + PAGE_SIZE)} disabled={offset + PAGE_SIZE >= actions.data.total}>Next<ArrowRight size={14}/></Button></div></footer>
    </>}
  </section>;
}

function RequestActionForm({ tickets, ticketsLoading, onSuccess }: { tickets: Ticket[]; ticketsLoading: boolean; onSuccess: (action: CommerceAction) => Promise<void> }) {
  const [ticketId, setTicketId] = useState("");
  const [actionType, setActionType] = useState<"refund" | "cancel">("refund");
  const [orderNumber, setOrderNumber] = useState("");
  const [refundAmount, setRefundAmount] = useState("");
  const [reason, setReason] = useState("");
  const [formError, setFormError] = useState<string>();
  const idempotencyKey = useRef<string | null>(null);
  const mutation = useMutation({ mutationFn: ({ payload, key }: { payload: Parameters<typeof createCommerceAction>[0]; key: string }) => createCommerceAction(payload, key), onSuccess });

  function clearRetryKey() {
    idempotencyKey.current = null;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(undefined);
    const ticket = tickets.find((item) => item.id === ticketId);
    const normalizedOrder = orderNumber.trim();
    if (!ticketId || !ticket) return setFormError("Choose a ticket for the customer whose order you are requesting.");
    if (!/^[#]?[A-Za-z0-9-]+$/.test(normalizedOrder)) return setFormError("Enter a valid Shopify order number.");
    if (actionType === "refund" && (!Number.isFinite(Number(refundAmount)) || Number(refundAmount) <= 0)) return setFormError("Enter a refund amount greater than zero.");
    if (reason.trim().length < 5) return setFormError("Add a reason with at least five characters.");
    const payload = {
      ticket_id: ticketId,
      order_number: normalizedOrder,
      action_type: actionType,
      ...(actionType === "refund" ? { refund_amount: Number(refundAmount) } : {}),
      reason: reason.trim(),
    } as Parameters<typeof createCommerceAction>[0];
    const key = idempotencyKey.current ?? crypto.randomUUID();
    idempotencyKey.current = key;
    try {
      await mutation.mutateAsync({ payload, key });
      setOrderNumber("");
      setRefundAmount("");
      setReason("");
      clearRetryKey();
    } catch {
      // Keep the same key on retry so an ambiguous network response cannot
      // create a second order action.
    }
  }

  const error = formError ?? (mutation.error instanceof ApiError ? mutation.error.message : mutation.isError ? "The request could not be submitted. Retry to safely check the same request." : undefined);
  return <form onSubmit={submit} className="rounded-2xl border border-blue-100 bg-blue-50/40 p-4 sm:p-5">
    <div className="mb-4 flex items-start gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-white text-blue-700"><ShieldCheck size={18}/></span><div><h3 className="font-semibold text-slate-900">Request a refund or cancellation</h3><p className="mt-1 text-xs leading-5 text-slate-600">Order number and ticket-linked customer are verified by Shopify before the request enters the approval queue.</p></div></div>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <label className="space-y-1.5 text-xs font-semibold text-slate-700"><span>Support ticket</span><Select aria-label="Support ticket" required value={ticketId} disabled={ticketsLoading} onChange={(event) => { clearRetryKey(); setTicketId(event.target.value); }}><option value="">{ticketsLoading ? "Loading tickets…" : "Choose ticket"}</option>{tickets.map((ticket) => <option key={ticket.id} value={ticket.id}>{ticket.subject} · {ticket.customer_name ?? "Customer"}</option>)}</Select></label>
      <label className="space-y-1.5 text-xs font-semibold text-slate-700"><span>Action</span><Select aria-label="Action type" value={actionType} onChange={(event) => { clearRetryKey(); setActionType(event.target.value as "refund" | "cancel"); }}><option value="refund">Refund</option><option value="cancel">Cancellation</option></Select></label>
      <label className="space-y-1.5 text-xs font-semibold text-slate-700"><span>Shopify order number</span><Input aria-label="Shopify order number" value={orderNumber} placeholder="#1001" required onChange={(event) => { clearRetryKey(); setOrderNumber(event.target.value); }}/></label>
      {actionType === "refund" && <label className="space-y-1.5 text-xs font-semibold text-slate-700"><span>Refund amount</span><Input aria-label="Refund amount" type="number" inputMode="decimal" min="0.01" step="0.01" value={refundAmount} required onChange={(event) => { clearRetryKey(); setRefundAmount(event.target.value); }}/></label>}
    </div>
    <label className="mt-3 block space-y-1.5 text-xs font-semibold text-slate-700"><span>Reason for review</span><Textarea aria-label="Reason for review" rows={2} minLength={5} maxLength={500} value={reason} required placeholder="Describe the customer issue and requested resolution." onChange={(event) => { clearRetryKey(); setReason(event.target.value); }}/></label>
    {error && <p role="alert" className="mt-3 flex items-start gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-800"><CircleAlert size={16} className="mt-0.5 shrink-0"/>{error}</p>}
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-slate-500">Approved operations are simulated. SupportPilot never sends refund or cancellation writes to Shopify.</p><Button type="submit" disabled={mutation.isPending || ticketsLoading}>{mutation.isPending ? <><RefreshCw size={15} className="animate-spin"/>Submitting…</> : "Submit for approval"}</Button></div>
  </form>;
}

function ActionDetails({ action, audit, auditLoading, isReviewer, currentUserId, busy, error, onApprove, onReject, onCancel }: {
  action: CommerceAction;
  audit: { id: string; actor_name: string | null; event_type: string; details: Record<string, unknown>; created_at: string }[];
  auditLoading: boolean;
  isReviewer: boolean;
  currentUserId?: string;
  busy: boolean;
  error: unknown;
  onApprove: () => void;
  onReject: () => void;
  onCancel: () => void;
}) {
  const canCancel = action.approval_status === "pending" && (isReviewer || action.requested_by_user_id === currentUserId);
  const decisionMessage = error instanceof ApiError ? error.message : error ? "The review action could not be completed." : undefined;
  return <aside aria-label="Selected order operation" className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
    <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Selected request</p><h3 className="mt-1 text-lg font-bold capitalize">{action.action_type} · {action.order_number}</h3></div><span className="grid size-9 place-items-center rounded-xl bg-white text-blue-700"><Clock3 size={18}/></span></div>
    <dl className="mt-4 grid grid-cols-2 gap-2 text-xs"><Fact label="Approval" value={action.approval_status}/><Fact label="Execution" value={action.execution_status}/><Fact label="Requested by" value={action.requested_by_name}/><Fact label="Order total" value={`${action.order_total} ${action.currency}`}/>{action.refund_amount && <Fact label="Requested amount" value={`${action.refund_amount} ${action.currency}`}/>}</dl>
    <p className="mt-3 rounded-xl bg-white p-3 text-sm text-slate-700">{action.reason}</p>
    {action.correlation_id && <p className="mt-2 text-xs text-slate-500">Support reference: <SupportTraceLink correlationId={action.correlation_id} /></p>}
    {action.execution_error_code && <p role="alert" className="mt-2 text-xs text-red-700">Execution failed: {action.execution_error_code}</p>}
    {decisionMessage && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-2 text-xs text-red-700">{decisionMessage}</p>}
    {action.approval_status === "pending" && <div className="mt-3 flex flex-wrap gap-2">
      {isReviewer && <><Button size="sm" onClick={onApprove} disabled={busy}><BadgeCheck size={14}/>Approve</Button><Button size="sm" variant="danger" onClick={onReject} disabled={busy}><XCircle size={14}/>Reject</Button></>}
      {canCancel && <Button size="sm" variant="secondary" onClick={onCancel} disabled={busy}><Ban size={14}/>Cancel request</Button>}
    </div>}
    <div className="mt-5 border-t border-slate-200 pt-4"><h4 className="text-sm font-semibold">Audit history</h4>
      {auditLoading && <p role="status" className="mt-2 text-xs text-slate-500">Loading audit history…</p>}
      {!auditLoading && audit.length === 0 && <p className="mt-2 text-xs text-slate-500">No audit entries found.</p>}
      <ol className="mt-3 space-y-3">{audit.map((event) => <li key={event.id} className="relative border-l border-slate-200 pl-3"><span className="absolute -left-1 top-1 size-2 rounded-full bg-blue-500"/><p className="text-xs font-semibold capitalize text-slate-800">{event.event_type.replaceAll("_", " ")}</p><p className="mt-0.5 text-[11px] text-slate-500">{event.actor_name ?? "System"} · {new Date(event.created_at).toLocaleString()}</p></li>)}</ol>
    </div>
  </aside>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg bg-white p-2"><dt className="text-[10px] uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 font-semibold capitalize text-slate-800">{value}</dd></div>;
}

function StatusBadge({ value }: { value: string }) {
  const done = value === "succeeded" || value === "approved";
  const danger = value === "failed" || value === "rejected" || value === "expired";
  const klass = done ? "bg-emerald-50 text-emerald-700" : danger ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-800";
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-semibold capitalize ${klass}`}>{value.replaceAll("_", " ")}</span>;
}
