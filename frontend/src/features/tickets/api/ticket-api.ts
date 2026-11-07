import { api } from "@/lib/api/client";
import type { Ticket, TicketActivity } from "../types/ticket.types";
import type { Page } from "@/types/pagination";
import type { z } from "zod";
import type { createTicketSchema, updateTicketSchema } from "../schemas/ticket.schema";
import type { components } from "@/lib/api/generated";

export const ticketQueryKeys = {
  all: ["tickets"] as const,
  detail: (id: string) => ["ticket", id] as const,
  activity: (id: string) => ["ticket-activity", id] as const,
  stats: ["ticket-stats"] as const,
};

export const listTickets = (params: string) => api<Page<Ticket>>(`/tickets?${params}`);
type BulkTicketWire = components["schemas"]["TicketBulkUpdate"];
export type BulkTicketChanges = Omit<BulkTicketWire, "status" | "priority"> & {
  status?: Ticket["status"];
  priority?: Ticket["priority"];
  team_id?: string | null;
};
export const bulkUpdateTickets = (changes: BulkTicketChanges) =>
  api<components["schemas"]["TicketBulkUpdateOut"]>("/tickets/bulk", {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
export const listTicketLinks = (ticketId: string, limit = 50, offset = 0) =>
  api<components["schemas"]["TicketLinkPage"]>(`/tickets/${ticketId}/links?limit=${limit}&offset=${offset}`);
export const searchTicketLinkCandidates = (ticketId: string, params: string) =>
  api<Page<Ticket>>(`/tickets/${encodeURIComponent(ticketId)}/link-candidates?${params}`);
export const createTicketLink = (ticketId: string, relatedTicketId: string) =>
  api<components["schemas"]["TicketLinkOut"]>(`/tickets/${ticketId}/links`, {
    method: "POST",
    body: JSON.stringify({ related_ticket_id: relatedTicketId }),
  });
export const removeTicketLink = (ticketId: string, linkId: string) =>
  api<void>(`/tickets/${ticketId}/links/${linkId}`, { method: "DELETE" });
export const getTicket = (id: string) => api<Ticket>(`/tickets/${id}`);
export const createTicket = (values: z.infer<typeof createTicketSchema>) =>
  api<Ticket>("/tickets", { method: "POST", body: JSON.stringify(values) });
export const updateTicket = (id: string, changes: z.infer<typeof updateTicketSchema>) =>
  api<Ticket>(`/tickets/${id}`, { method: "PATCH", body: JSON.stringify(changes) });
export const assignTicketToMe = (id: string) =>
  api<Ticket>(`/tickets/${id}/assign-to-me`, { method: "POST" });
export const getTicketActivity = (id: string) => api<TicketActivity[]>(`/tickets/${id}/activity`);
