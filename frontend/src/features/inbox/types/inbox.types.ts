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
  team: { id: string; name: string; is_active: boolean } | null;
  latestMessage: { preview: string; createdAt: string; senderType: string } | null;
  unreadCount: number;
  firstResponseSla: InboxWireItem["first_response_sla"];
  updatedAt: string;
}

export type InboxScope = "all" | "mine" | "unassigned" | "my_teams";

export function mapInboxItem(item: InboxWireItem): InboxItem {
  return {
    ticketId: item.ticket_id,
    conversationId: item.conversation_id,
    subject: item.subject,
    status: item.status,
    priority: item.priority,
    customer: { id: item.customer.id, name: item.customer.name, email: item.customer.email },
    assignee: item.assignee ? { id: item.assignee.id, name: item.assignee.name } : null,
    team: item.team ? { id: item.team.id, name: item.team.name, is_active: item.team.is_active } : null,
    latestMessage: item.latest_message
      ? { preview: item.latest_message.preview, createdAt: item.latest_message.created_at, senderType: item.latest_message.sender_type }
      : null,
    unreadCount: item.unread_count,
    firstResponseSla: item.first_response_sla,
    updatedAt: item.updated_at,
  };
}
