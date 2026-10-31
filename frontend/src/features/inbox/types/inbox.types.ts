import type { components } from "@/lib/api/generated";

export type InboxWireItem = components["schemas"]["InboxItemOut"];
export type InboxWirePage = components["schemas"]["InboxPage"];

export interface InboxItem {
  ticketId: string;
  conversationId: string | null;
  subject: string;
  status: InboxWireItem["status"];
  priority: InboxWireItem["priority"];
  customer: { id: string; name: string; email: string | null };
  assignee: { id: string; name: string } | null;
  latestMessage: { preview: string; createdAt: string; senderType: string } | null;
  unreadCount: number;
  updatedAt: string;
}

export type InboxScope = "all" | "mine" | "unassigned";

export function mapInboxItem(item: InboxWireItem): InboxItem {
  return {
    ticketId: item.ticket_id,
    conversationId: item.conversation_id,
    subject: item.subject,
    status: item.status,
    priority: item.priority,
    customer: { id: item.customer.id, name: item.customer.name, email: item.customer.email },
    assignee: item.assignee ? { id: item.assignee.id, name: item.assignee.name } : null,
    latestMessage: item.latest_message
      ? { preview: item.latest_message.preview, createdAt: item.latest_message.created_at, senderType: item.latest_message.sender_type }
      : null,
    unreadCount: item.unread_count,
    updatedAt: item.updated_at,
  };
}
