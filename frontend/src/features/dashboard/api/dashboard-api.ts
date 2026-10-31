import { api } from "@/lib/api/client";
import type { TicketStats } from "@/features/tickets/types/ticket.types";

export const dashboardQueryKeys = { stats: ["ticket-stats"] as const };
export const getDashboardStats = () => api<TicketStats>("/tickets/stats");
