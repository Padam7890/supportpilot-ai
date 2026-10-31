import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type CommerceAction = components["schemas"]["CommerceActionOut"];
export type CommerceActionPage = components["schemas"]["CommerceActionPage"];
export type CommerceActionAuditPage = components["schemas"]["CommerceActionAuditPage"];
export type CommerceActionInput = components["schemas"]["CommerceActionCreate"];

export const commerceActionKeys = {
  list: (approvalStatus: string | undefined, offset: number, ticketId?: string) => ["commerce-actions", approvalStatus, offset, ticketId] as const,
  audit: (id: string) => ["commerce-action-audit", id] as const,
};

export function listCommerceActions(approvalStatus?: string, offset = 0, ticketId?: string) {
  const query = new URLSearchParams({ limit: "25", offset: String(offset) });
  if (approvalStatus) query.set("approval_status", approvalStatus);
  if (ticketId) query.set("ticket_id", ticketId);
  return api<CommerceActionPage>(`/commerce/actions?${query.toString()}`);
}

export const createCommerceAction = (values: CommerceActionInput, idempotencyKey: string) =>
  api<CommerceAction>("/commerce/actions", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(values),
  });

export const approveCommerceAction = (id: string) =>
  api<CommerceAction>(`/commerce/actions/${encodeURIComponent(id)}/approve`, { method: "POST" });

export const rejectCommerceAction = (id: string) =>
  api<CommerceAction>(`/commerce/actions/${encodeURIComponent(id)}/reject`, { method: "POST" });

export const cancelCommerceAction = (id: string) =>
  api<CommerceAction>(`/commerce/actions/${encodeURIComponent(id)}/cancel`, { method: "POST" });

export const getCommerceActionAudit = (id: string) =>
  api<CommerceActionAuditPage>(`/commerce/actions/${encodeURIComponent(id)}/audit?limit=100&offset=0`);
