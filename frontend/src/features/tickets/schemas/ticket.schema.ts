import { z } from "zod";

export const createTicketSchema = z.object({
  customer_id: z.string().uuid("Choose a customer"),
  subject: z.string().min(3).max(240),
  description: z.string().optional(),
  priority: z.enum(["low", "normal", "high", "urgent"]),
});

export const updateTicketSchema = z.object({
  status: z.enum(["open", "pending", "resolved", "closed"]).optional(),
  priority: z.enum(["low", "normal", "high", "urgent"]).optional(),
  assignee_id: z.string().uuid().nullable().optional(),
});
