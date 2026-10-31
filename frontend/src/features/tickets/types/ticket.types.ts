export type Ticket = {
  id: string;
  organization_id: string;
  customer_id: string;
  assignee_id: string | null;
  subject: string;
  description: string | null;
  status: "open" | "pending" | "resolved" | "closed";
  priority: "low" | "normal" | "high" | "urgent";
  customer_name: string | null;
  assignee_name: string | null;
  created_at: string;
  updated_at: string;
};

export type TicketActivity = {
  id: string;
  ticket_id: string;
  actor_user_id: string | null;
  actor_name: string | null;
  activity_type: string;
  details: Record<string, { from: string | null; to: string | null } | string>;
  created_at: string;
};

export type TicketStats = {
  total_tickets: number;
  open_tickets: number;
  pending_tickets: number;
  resolved_tickets: number;
  closed_tickets: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  volume: { date: string; count: number }[];
};
