import { api } from "@/lib/api/client";
import type { Ticket, TicketActivity } from "../types/ticket.types";
import type { Page } from "@/types/pagination";
import type { z } from "zod";
import type { createTicketSchema, updateTicketSchema } from "../schemas/ticket.schema";

export const ticketQueryKeys = {
  all: ["tickets"] as const,
  detail: (id: string) => ["ticket", id] as const,
  activity: (id: string) => ["ticket-activity", id] as const,
  stats: ["ticket-stats"] as const,
};

export const listTickets = (params: string) => api<Page<Ticket>>(`/tickets?${params}`);
export const getTicket = (id: string) => api<Ticket>(`/tickets/${id}`);
export const createTicket = (values: z.infer<typeof createTicketSchema>) =>
  api<Ticket>("/tickets", { method: "POST", body: JSON.stringify(values) });
export const updateTicket = (id: string, changes: z.infer<typeof updateTicketSchema>) =>
  api<Ticket>(`/tickets/${id}`, { method: "PATCH", body: JSON.stringify(changes) });
export const getTicketActivity = (id: string) => api<TicketActivity[]>(`/tickets/${id}/activity`);
