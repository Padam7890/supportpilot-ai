"use client";

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

export function ShopifyCancellationPanel({ ticketId }: { ticketId: string }) {
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
    refetchInterval: (query) => query.state.data?.items.some((action) => action.execution_status === "queued" || action.execution_status === "running") && typeof document !== "undefined" && document.visibilityState === "visible" ? 2500 : false,
    refetchIntervalInBackground: false,
  });
  const rows = actions.data?.items.filter((action) => action.provider === "shopify") ?? [];
  const selected = rows.find((action) => action.id === selectedId) ?? rows[0];
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

  return <Panel>
    <PanelHeader title="Shopify cancellation" description="Customer-verified requests require Owner/Admin approval before Shopify is changed." action={<ShieldCheck size={16} className="text-blue-700"/>}/>
    <PanelBody className="space-y-4">
      {status.isPending && <p role="status" className="text-xs text-slate-500">Checking Shopify connection…</p>}
      {status.isError && <p role="alert" className="text-xs text-red-700">Shopify connection status could not be checked.</p>}
      {!status.isPending && !status.isError && !connected && <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">Connect a Shopify store before requesting a cancellation.</p>}
      {connected && !hasWriteOrders && <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">This store connection does not have the Shopify write_orders permission required for cancellations.</p>}
      {canRequest && connected && hasWriteOrders && <form onSubmit={submit} className="space-y-3 rounded-xl border border-slate-200 p-3">
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
      </form>}
      {actions.isPending && <div role="status" className="h-12 animate-pulse rounded-lg bg-slate-100"/>}
      {actions.isError && <p role="alert" className="text-xs text-red-700">Cancellation requests for this ticket could not be loaded.</p>}
      {rows.length === 0 && !actions.isPending && !actions.isError && <p className="text-xs text-slate-500">No Shopify cancellation requests for this ticket.</p>}
      {rows.length > 0 && <div className="space-y-2">
        <ul aria-label="Shopify cancellation requests" className="space-y-2">{rows.map((action) => <li key={action.id}><button type="button" aria-pressed={selected?.id === action.id} onClick={() => setSelectedId(action.id)} className={`w-full rounded-lg border p-3 text-left ${selected?.id === action.id ? "border-blue-300 bg-blue-50" : "border-slate-200 hover:bg-slate-50"}`}><span className="flex flex-wrap items-center justify-between gap-1"><strong className="text-xs">{action.order_number} · {action.approval_status}</strong><span className="text-[10px] capitalize text-slate-500">{action.execution_status === "running" ? "executing" : action.execution_status}</span></span><span className="mt-1 block text-[11px] text-slate-500">Requested by {action.requested_by_name} · {formatDateTime(action.created_at)}</span></button></li>)}</ul>
        {selected && <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
          <p className="font-semibold text-slate-900">{selected.order_number} · {selected.order_total} {selected.currency}</p>
          <p className="mt-1 text-slate-600">{selected.reason}</p>
          <dl className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-slate-600"><Fact label="Refund" value={selected.cancel_refund ? "Original payment method" : "No refund"}/><Fact label="Inventory" value={selected.cancel_restock ? "Restock" : "Do not restock"}/><Fact label="Customer" value={selected.cancel_notify_customer ? "Notify" : "Do not notify"}/></dl>
          {selected.execution_error_code && <p role="alert" className="mt-2 text-red-700">{selected.execution_error_code}</p>}
          {selected.execution_status === "succeeded" && <p role="status" className="mt-2 font-semibold text-emerald-700">Shopify confirmed the cancellation.</p>}
          {selected.approval_status === "pending" && <div className="mt-3 flex gap-2">{canReview && <><Button size="sm" onClick={() => approveSelected(selected)} disabled={actionBusy}><BadgeCheck size={13}/>Approve & execute</Button><Button size="sm" variant="danger" onClick={() => reject.mutate(selected.id)} disabled={actionBusy}><XCircle size={13}/>Reject</Button></>}{(canReview || selected.requested_by_user_id === me.data?.id) && <Button size="sm" variant="secondary" onClick={() => cancel.mutate(selected.id)} disabled={actionBusy}><Ban size={13}/>Withdraw</Button>}</div>}
          {audit.data?.items.map((entry) => <p key={entry.id} className="mt-2 text-[10px] text-slate-500">{entry.event_type.replaceAll("_", " ")} · {entry.actor_name ?? "System"} · {formatDateTime(entry.created_at)}</p>)}
        </div>}
      </div>}
    </PanelBody>
  </Panel>;
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="flex items-start gap-2 text-xs font-medium text-slate-700"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="mt-0.5"/><span>{label}</span></label>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-2"><dt>{label}</dt><dd className="font-medium">{value}</dd></div>;
}
