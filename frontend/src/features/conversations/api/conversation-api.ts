import { api } from "@/lib/api/client";
import type { Conversation, Message } from "../types/conversation.types";
import type { SendMessageValues } from "../schemas/conversation.schema";

export const conversationQueryKeys = {
  byTicket: (ticketId: string) => ["conversations", ticketId] as const,
  messages: (conversationId: string | undefined) => ["messages", conversationId] as const,
};

export const listConversations = (ticketId: string) => api<Conversation[]>(`/tickets/${ticketId}/conversations`);
export const startConversation = (ticketId: string) =>
  api<Conversation>(`/tickets/${ticketId}/conversations`, { method: "POST", body: JSON.stringify({ channel: "web" }) });
export const listMessages = (conversationId: string) => api<Message[]>(`/conversations/${conversationId}/messages`);
export const sendMessage = (conversationId: string, values: SendMessageValues) =>
  api<Message>(`/conversations/${conversationId}/messages`, { method: "POST", body: JSON.stringify(values) });
