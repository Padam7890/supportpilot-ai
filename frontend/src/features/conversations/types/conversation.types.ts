export type Conversation = {
  id: string;
  ticket_id: string;
  channel: string;
  status: string;
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
};
