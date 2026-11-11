import { describe, expect, it } from "vitest";
import { mapInboxItem, type InboxWireItem } from "./inbox.types";

describe("mapInboxItem", () => {
  it("maps the snake_case OpenAPI inbox response to the frontend view model", () => {
    const wire: InboxWireItem = {
      ticket_id: "ticket-1",
      conversation_id: "conversation-1",
      subject: "Order status",
      status: "open",
      priority: "urgent",
      customer: { id: "customer-1", name: "Taylor", email: "taylor@example.com" },
      assignee: { id: "agent-1", name: "Morgan" },
      latest_message: { preview: "Can you help?", created_at: "2026-10-31T10:00:00Z", sender_type: "customer" },
      unread_count: 2,
      updated_at: "2026-10-31T10:00:00Z",
    };

    expect(mapInboxItem(wire)).toEqual({
      ticketId: "ticket-1",
      conversationId: "conversation-1",
      subject: "Order status",
      status: "open",
      priority: "urgent",
      customer: { id: "customer-1", name: "Taylor", email: "taylor@example.com" },
      assignee: { id: "agent-1", name: "Morgan" },
      team: null,
      firstResponseSla: undefined,
      latestMessage: { preview: "Can you help?", createdAt: "2026-10-31T10:00:00Z", senderType: "customer" },
      unreadCount: 2,
      updatedAt: "2026-10-31T10:00:00Z",
    });
  });

  it("preserves null conversation and assignment values", () => {
    const wire: InboxWireItem = {
      ticket_id: "ticket-2",
      conversation_id: null,
      subject: "New request",
      status: "open",
      priority: "normal",
      customer: { id: "customer-2", name: "Jamie", email: null },
      assignee: null,
      latest_message: null,
      unread_count: 0,
      updated_at: "2026-10-31T10:00:00Z",
    };
    const item = mapInboxItem(wire);
    expect(item.conversationId).toBeNull();
    expect(item.assignee).toBeNull();
    expect(item.latestMessage).toBeNull();
  });
});
