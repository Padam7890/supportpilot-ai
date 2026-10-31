export type Customer = {
  id: string;
  organization_id: string;
  name: string;
  email: string;
  phone: string | null;
  external_reference: string | null;
  created_at: string;
  updated_at: string;
};

export type CustomerMessageHistoryItem = {
  id: string;
  ticket_id: string;
  ticket_subject: string;
  conversation_id: string;
  sender_type: string;
  sender_name: string | null;
  content: string;
  created_at: string;
};
