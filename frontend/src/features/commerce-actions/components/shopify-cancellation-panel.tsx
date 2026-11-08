"use client";

import { Checkbox } from "@/components/ui";
import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BadgeCheck, Ban, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getCurrentUser, currentUserQueryKey } from "@/features/auth/api/auth-api";
import { getShopifyStatus, shopifyQueryKeys } from "@/features/integrations/api/shopify-api";
import { formatDateTime } from "@/lib/utils";
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

export function ShopifyCancellationPanel({ ticketId, compact = false }: { ticketId: string; compact?: boolean }) {
  const client = useQueryClient();
  const me = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const status = useQuery({ queryKey: shopifyQueryKeys.status, queryFn: getShopifyStatus });
  const [selectedId, setSelectedId] = useState<string>();
  const [orderNumber, setOrderNumber] = useState("");
  const [reason, setReason] = useState("");
  const [refund, setRefund] = useState(false);
  const [restock, setRestock] = useState(false);
  const [notify, setNotify] = useState(false);
  const [formError, setFormError] = useState<string>();
  const keyRef = useRef<string | undefined>(undefined);
  const canRequest = ["owner", "admin", "agent"].includes(me.data?.role ?? "");
  const canReview = ["owner", "admin"].includes(me.data?.role ?? "");
  const actions = useQuery({
    queryKey: commerceActionKeys.list(undefined, 0, ticketId),
    queryFn: () => listCommerceActions(undefined, 0, ticketId),
    refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 10_000 : false,
    refetchIntervalInBackground: false,
  });
  const actionItems = actions.data && Array.isArray(actions.data.items) ? actions.data.items : [];
  const rows = actionItems.filter((action) => action.provider === "shopify");
  const pendingRows = rows.filter((action) => action.approval_status === "pending");
  const historyRows = rows.filter((action) => action.approval_status !== "pending");
  const selected = historyRows.find((action) => action.id === selectedId) ?? historyRows[0];
  const audit = useQuery({ queryKey: commerceActionKeys.audit(selected?.id ?? ""), queryFn: () => getCommerceActionAudit(selected!.id), enabled: Boolean(selected) });
  const refresh = async (action?: CommerceAction) => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["commerce-actions"] }),
      client.invalidateQueries({ queryKey: ["inbox"] }),
      client.invalidateQueries({ queryKey: shopifyQueryKeys.orderPages() }),
      ...(action ? [client.invalidateQueries({ queryKey: commerceActionKeys.audit(action.id) })] : []),
    ]);
  };
  const create = useMutation({
    mutationFn: (idempotencyKey: string) => createCommerceAction({
      ticket_id: ticketId,
      order_number: orderNumber.trim(),
      action_type: "cancel",
      provider: "shopify",
      reason: reason.trim(),
      cancel_refund: refund,
      cancel_restock: restock,
      cancel_notify_customer: notify,
      cancellation_reason: "CUSTOMER",
    }, idempotencyKey),
    onSuccess: async (action) => {
      setSelectedId(action.id);
      setOrderNumber(""); setReason(""); setRefund(false); setRestock(false); setNotify(false); keyRef.current = undefined;
      await refresh(action);
    },
  });
  const approve = useMutation({ mutationFn: approveCommerceAction, onSuccess: refresh });
  const reject = useMutation({ mutationFn: rejectCommerceAction, onSuccess: refresh });
  const cancel = useMutation({ mutationFn: cancelCommerceAction, onSuccess: refresh });
  const actionBusy = approve.isPending || reject.isPending || cancel.isPending;
  const connected = status.data?.connected === true;
  const hasWriteOrders = status.data?.granted_scopes?.includes("write_orders") === true;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setFormError(undefined);
    if (!/^#?[A-Za-z0-9-]{1,60}$/.test(orderNumber.trim())) return setFormError("Enter a valid Shopify order number.");
    if (reason.trim().length < 5) return setFormError("Add a reason with at least five characters.");
    keyRef.current ??= crypto.randomUUID();
    create.mutate(keyRef.current);
  }

  function approveSelected(action: CommerceAction) {
    const consequences = [
      action.cancel_refund ? "refund to original payment method" : "no refund",
      action.cancel_restock ? "restock inventory" : "do not restock inventory",
      action.cancel_notify_customer ? "send customer notification" : "do not notify customer",
    ].join(", ");
    if (window.confirm(`Shopify cancellation is irreversible. Approve cancellation of ${action.order_number} with these consequences: ${consequences}?`)) approve.mutate(action.id);
  }

  if (compact) {
    if (actions.isPending) return <div role="status" className="h-9 animate-pulse rounded-lg bg-amber-50"/>;
    if (actions.isError) return <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">Could not load order approvals for this ticket.</p>;
    if (pendingRows.length === 0) return null;

    return <section aria-label="Order approvals" className="max-h-40 overflow-y-auto rounded-xl border border-amber-200 bg-amber-50 p-2.5 shadow-sm">
      {pendingRows.length > 0 && <div className="space-y-2">
        <div className="flex items-center justify-between gap-2 px-1"><p className="text-xs font-bold text-amber-700">Needs approval <span className="ml-1 rounded-full bg-amber-200 px-1.5 py-0.5">{pendingRows.length}</span></p><p className="text-[10px] text-amber-700">Owner/Admin</p></div>
        {pendingRows.map((action) => <article key={action.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-amber-100 bg-white px-3 py-2">
          <div className="min-w-32 flex-1"><p className="text-xs font-bold text-slate-900">Cancel {action.order_number}</p><p className="truncate text-[11px] text-slate-600">{action.reason}</p><p className="text-[10px] text-slate-400">{action.cancel_refund ? "Refund" : "No refund"} · {action.cancel_restock ? "Restock" : "No restock"} · {action.cancel_notify_customer ? "Notify" : "No notification"}</p></div>
          {canReview ? <div className="flex shrink-0 gap-1.5"><Button size="sm" className="h-8 px-2.5 text-xs" onClick={() => approveSelected(action)} disabled={actionBusy}><BadgeCheck size={13}/>{approve.isPending ? "Approving…" : "Approve"}</Button><Button size="sm" variant="danger" className="h-8 px-2.5 text-xs" onClick={() => reject.mutate(action.id)} disabled={actionBusy}><XCircle size={13}/>{reject.isPending ? "Rejecting…" : "Reject"}</Button></div> : <span className="text-[10px] text-slate-500">Owner/Admin approval required</span>}
        </article>)}
      </div>}
      {(approve.isError || reject.isError) && <p role="alert" className="px-1 pt-1 text-xs text-red-700">{approve.error instanceof ApiError ? approve.error.message : reject.error instanceof ApiError ? reject.error.message : "The cancellation review could not be completed."}</p>}
    </section>;
  }

  return <Panel>
    <PanelHeader title="Order requests" description="Cancellation review and history." action={<ShieldCheck size={16} className="text-blue-700"/>}/>
    <PanelBody className="space-y-4">
      {status.isPending && <p role="status" className="text-xs text-slate-500">Checking Shopify connection…</p>}
      {status.isError && <p role="alert" className="text-xs text-red-700">Shopify connection status could not be checked.</p>}
      {!status.isPending && !status.isError && !connected && <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">Connect a Shopify store before requesting a cancellation.</p>}
      {connected && !hasWriteOrders && <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">This store connection does not have the Shopify write_orders permission required for cancellations.</p>}
      {pendingRows.length > 0 && <section aria-label="Cancellation requests awaiting review" className="space-y-3 rounded-xl border border-amber-300 bg-amber-50 p-3">
        <div className="flex items-center gap-2"><span className="grid size-8 shrink-0 place-items-center rounded-lg bg-white text-amber-700"><AlertTriangle size={16}/></span><div className="min-w-0"><p className="text-sm font-semibold text-amber-950">Needs review <span className="ml-1 rounded-full bg-amber-200 px-1.5 py-0.5 text-[10px]">{pendingRows.length}</span></p><p className="text-[11px] text-amber-900">Owner/Admin approval required</p></div></div>
        {pendingRows.map((action) => <article key={action.id} className="rounded-lg border border-amber-200 bg-white p-3">
          <div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="truncate text-sm font-bold text-slate-900">Cancel {action.order_number}</p><p className="mt-0.5 text-xs text-slate-500">{action.order_total} {action.currency} · {formatDateTime(action.created_at)}</p></div><span className="shrink-0 rounded-full bg-amber-100 px-2 py-1 text-[10px] font-bold text-amber-900">Pending</span></div>
          <p className="mt-2 line-clamp-3 break-words text-xs leading-5 text-slate-700">{action.reason}</p>
          <div className="mt-2 rounded-md bg-slate-50 p-2 text-[10px] leading-4 text-slate-600">{action.cancel_refund ? "Refund" : "No refund"} · {action.cancel_restock ? "Restock" : "No restock"} · {action.cancel_notify_customer ? "Notify" : "No notification"}</div>
          {canReview ? <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2"><Button size="sm" className="w-full whitespace-normal" onClick={() => approveSelected(action)} disabled={actionBusy}><BadgeCheck size={14}/>{approve.isPending ? "Approving…" : "Approve & execute"}</Button><Button size="sm" variant="danger" className="w-full" onClick={() => reject.mutate(action.id)} disabled={actionBusy}><XCircle size={14}/>{reject.isPending ? "Rejecting…" : "Reject"}</Button></div> : <p className="mt-3 text-xs font-medium text-amber-900">Only an Owner or Admin can review this request.</p>}
        </article>)}
        {(approve.isError || reject.isError) && <p role="alert" className="text-xs font-medium text-red-700">{approve.error instanceof ApiError ? approve.error.message : reject.error instanceof ApiError ? reject.error.message : "The cancellation review could not be completed."}</p>}
      </section>}
      {canRequest && connected && hasWriteOrders && <details className="rounded-xl border border-slate-200 bg-white">
        <summary className="cursor-pointer list-none px-3 py-3 text-xs font-semibold text-slate-700 marker:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">+ Create a cancellation request</summary>
        <form onSubmit={submit} className="space-y-3 border-t border-slate-100 p-3">
        <label className="block space-y-1 text-xs font-semibold text-slate-700"><span>Shopify order number</span><Input aria-label="Cancellation order number" placeholder="#1001" value={orderNumber} onChange={(event) => setOrderNumber(event.target.value)}/></label>
        <label className="block space-y-1 text-xs font-semibold text-slate-700"><span>Reason</span><Textarea aria-label="Cancellation reason" rows={2} maxLength={500} placeholder="Why is cancellation requested?" value={reason} onChange={(event) => setReason(event.target.value)}/></label>
        <fieldset className="space-y-2 rounded-lg bg-slate-50 p-3"><legend className="px-1 text-xs font-semibold text-slate-700">Requested consequences — approver must confirm these</legend>
          <Check label="Refund original payment method" checked={refund} onChange={setRefund}/>
          <Check label="Restock inventory" checked={restock} onChange={setRestock}/>
          <Check label="Notify the customer" checked={notify} onChange={setNotify}/>
        </fieldset>
        {formError && <p role="alert" className="text-xs text-red-700">{formError}</p>}
        {create.error && <p role="alert" className="text-xs text-red-700">{create.error instanceof ApiError ? create.error.message : "Cancellation request could not be submitted."}</p>}
        <p className="flex items-start gap-2 text-[11px] leading-4 text-amber-900"><AlertTriangle size={14} className="mt-0.5 shrink-0"/>Cancellation cannot be undone. Refunds, restocking, and customer notifications default off.</p>
        <Button type="submit" size="sm" className="w-full" disabled={!canRequest || create.isPending}>{create.isPending ? <><RefreshCw size={14} className="animate-spin"/>Submitting…</> : "Submit for approval"}</Button>
        </form>
      </details>}
      {actions.isPending && <div role="status" className="h-12 animate-pulse rounded-lg bg-slate-100"/>}
      {actions.isError && <p role="alert" className="text-xs text-red-700">Cancellation requests for this ticket could not be loaded.</p>}
      {!actions.isPending && !actions.isError && rows.length === 0 && !canRequest && <p className="text-xs text-slate-500">No Shopify cancellation requests for this ticket.</p>}
      {historyRows.length > 0 && <details className="rounded-xl border border-slate-200 bg-white"><summary className="cursor-pointer list-none px-3 py-3 text-xs font-semibold text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">Completed request history <span className="ml-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px]">{historyRows.length}</span></summary><div className="space-y-2 border-t border-slate-100 p-3">
        <ul aria-label="Completed Shopify cancellation requests" className="space-y-2">{historyRows.map((action) => <li key={action.id}><Button variant="unstyled" type="button" aria-pressed={selected?.id === action.id} onClick={() => setSelectedId(action.id)} className={`w-full rounded-lg border p-3 text-left ${selected?.id === action.id ? "border-blue-300 bg-blue-50" : "border-slate-200 hover:bg-slate-50"}`}><span className="flex flex-wrap items-center justify-between gap-1"><strong className="text-xs">{action.order_number} · {titleCase(action.approval_status)}</strong><span className="text-[10px] capitalize text-slate-500">{action.execution_status === "running" ? "executing" : action.execution_status.replaceAll("_", " ")}</span></span><span className="mt-1 block text-[11px] text-slate-500">{formatDateTime(action.created_at)}</span></Button></li>)}</ul>
        {selected && <div className="rounded-lg bg-slate-50 p-3 text-xs">
          <p className="font-semibold text-slate-900">{selected.order_number} · {selected.order_total} {selected.currency}</p>
          <p className="mt-1 text-slate-600">{selected.reason}</p>
          <dl className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-slate-600"><Fact label="Refund" value={selected.cancel_refund ? "Original payment method" : "No refund"}/><Fact label="Inventory" value={selected.cancel_restock ? "Restock" : "Do not restock"}/><Fact label="Customer" value={selected.cancel_notify_customer ? "Notify" : "Do not notify"}/></dl>
          {selected.execution_error_code && <p role="alert" className="mt-2 text-red-700">{selected.execution_error_code}</p>}
          {selected.execution_status === "succeeded" && <p role="status" className="mt-2 font-semibold text-emerald-700">Shopify confirmed the cancellation.</p>}
          {selected.approval_status === "pending" && <div className="mt-3 flex gap-2">{canReview && <><Button size="sm" onClick={() => approveSelected(selected)} disabled={actionBusy}><BadgeCheck size={13}/>Approve & execute</Button><Button size="sm" variant="danger" onClick={() => reject.mutate(selected.id)} disabled={actionBusy}><XCircle size={13}/>Reject</Button></>}{(canReview || selected.requested_by_user_id === me.data?.id) && <Button size="sm" variant="secondary" onClick={() => cancel.mutate(selected.id)} disabled={actionBusy}><Ban size={13}/>Withdraw</Button>}</div>}
          {audit.data?.items.map((entry) => <p key={entry.id} className="mt-2 text-[10px] text-slate-500">{entry.event_type.replaceAll("_", " ")} · {entry.actor_name ?? "System"} · {formatDateTime(entry.created_at)}</p>)}
        </div>}
      </div></details>}
    </PanelBody>
  </Panel>;
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="flex items-start gap-2 text-xs font-medium text-slate-700"><Checkbox checked={checked} onCheckedChange={(checked) => onChange(checked === true)} className="mt-0.5"/><span>{label}</span></label>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-2"><dt>{label}</dt><dd className="font-medium">{value}</dd></div>;
}

function titleCase(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
