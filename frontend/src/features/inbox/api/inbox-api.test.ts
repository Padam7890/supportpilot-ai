import { beforeEach, describe, expect, it, vi } from "vitest";
import { getInbox } from "./inbox-api";

const api = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/client", () => ({ api }));

describe("inbox API filters", () => {
  beforeEach(() => {
    api.mockReset();
    api.mockResolvedValue({ items: [], limit: 30, next_cursor: null });
  });

  it("sends unread and pending-approval filters to the server before pagination", async () => {
    await getInbox({
      scope: "mine",
      status: "open",
      priority: "urgent",
      search: "order issue",
      needsApproval: true,
      unreadOnly: true,
    }, "signed-cursor");

    expect(api).toHaveBeenCalledWith(
      "/inbox?scope=mine&limit=30&status=open&priority=urgent&needs_approval=true&unread_only=true&search=order+issue&cursor=signed-cursor",
    );
  });

  it("omits disabled filters and maps the API's snake_case page", async () => {
    api.mockResolvedValueOnce({
      items: [{
        ticket_id: "ticket-1",
        conversation_id: null,
        subject: "Question",
        status: "open",
        priority: "normal",
        customer: { id: "customer-1", name: "Casey", email: null },
        assignee: null,
        latest_message: null,
        unread_count: 0,
        updated_at: "2026-10-31T12:00:00Z",
      }],
      limit: 30,
      next_cursor: null,
    });

    const page = await getInbox({
      scope: "all",
      status: "",
      priority: "",
      search: "",
      needsApproval: false,
      unreadOnly: false,
    });

    expect(api).toHaveBeenCalledWith("/inbox?scope=all&limit=30");
    expect(page.items[0]).toMatchObject({
      ticketId: "ticket-1",
      conversationId: null,
      customer: { id: "customer-1", name: "Casey", email: null },
      unreadCount: 0,
    });
  });
});
