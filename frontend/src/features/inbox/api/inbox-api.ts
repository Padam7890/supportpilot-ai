import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";
import { mapInboxItem, type InboxScope, type InboxWirePage } from "../types/inbox.types";

export type InboxFilters = { scope: InboxScope; status: string; priority: string; search: string };
export type InboxPage = { items: ReturnType<typeof mapInboxItem>[]; limit: number; nextCursor: string | null };

export const inboxQueryKeys = {
  page: (filters: InboxFilters) => ["inbox", filters] as const,
  conversations: (ticketId: string | undefined) => ["inbox-conversations", ticketId] as const,
  messages: (conversationId: string | undefined) => ["inbox-messages", conversationId] as const,
};

export async function getInbox(filters: InboxFilters, cursor?: string): Promise<InboxPage> {
  const params = new URLSearchParams({ scope: filters.scope, limit: "30" });
  if (filters.status) params.set("status", filters.status);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.search.trim()) params.set("search", filters.search.trim());
  if (cursor) params.set("cursor", cursor);
  const page = await api<InboxWirePage>(`/inbox?${params.toString()}`);
  return { items: page.items.map(mapInboxItem), limit: page.limit, nextCursor: page.next_cursor };
}

export async function markConversationRead(conversationId: string) {
  return api<components["schemas"]["ConversationReadOut"]>(`/conversations/${conversationId}/read`, { method: "POST" });
}
