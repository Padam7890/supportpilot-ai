export type Conversation = {
  id: string;
  ticket_id: string;
  channel: string;
  status: string;
  ai_mode: "ai" | "human";
  ai_agent_id: string;
  ai_agent_override: boolean;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  sender_type: string;
  sender_user_id: string | null;
  sender_name: string | null;
  content: string;
  content_type: string;
  created_at: string;
  updated_at: string;
  delivery_status?: "received" | "accepted" | "sent" | "delivered" | "failed" | "unknown" | null;
  delivery_job_status?: "queued" | "running" | "succeeded" | "failed" | "cancelled" | null;
  delivery_error_code?: string | null;
  delivery_correlation_id?: string | null;
};
