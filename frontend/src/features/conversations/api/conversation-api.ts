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
export const listInternalNotes = (conversationId: string) => api<Message[]>(`/conversations/${conversationId}/notes`);
export const sendMessage = (conversationId: string, values: SendMessageValues) =>
  api<Message>(`/conversations/${conversationId}/messages`, { method: "POST", body: JSON.stringify(values) });
export const sendInternalNote = (conversationId: string, content: string) =>
  api<Message>(`/conversations/${conversationId}/notes`, { method: "POST", body: JSON.stringify({ content }) });
export const updateConversationAIMode = (conversationId: string, mode: "ai" | "human") =>
  api<Conversation>(`/conversations/${conversationId}/ai-mode`, { method: "PATCH", body: JSON.stringify({ mode }) });
export const updateConversationAIAgent = (conversationId: string, ai_agent_id: string | null) =>
  api<Conversation>(`/conversations/${conversationId}/ai-agent`, { method: "PATCH", body: JSON.stringify({ ai_agent_id }) });
