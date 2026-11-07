import { expect, test } from "@playwright/test";

test("agent can reply, add a private note, claim a ticket, and change its status", async ({ page }) => {
  const now = "2026-11-06T12:00:00.000Z";
  const ticket = {
    id: "ticket-1",
    organization_id: "org-1",
    customer_id: "customer-1",
    assignee_id: null as string | null,
    subject: "Delivery question",
    description: null,
    status: "open" as "open" | "resolved",
    priority: "normal",
    customer_name: "Taylor Customer",
    assignee_name: null as string | null,
    created_at: now,
    updated_at: now,
  };
  const conversation = {
    id: "conversation-1",
    ticket_id: ticket.id,
    channel: "web",
    status: "active",
    ai_mode: "human" as const,
    created_at: now,
    updated_at: now,
  };
  type TestMessage = {
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
  const messages: TestMessage[] = [{
    id: "customer-message-1",
    conversation_id: conversation.id,
    sender_type: "customer",
    sender_user_id: null,
    sender_name: "Taylor Customer",
    content: "Can you check my delivery?",
    content_type: "text",
    created_at: now,
    updated_at: now,
  }];
  const notes: typeof messages = [];
  let nextMessageId = 1;

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/auth/me") {
      await route.fulfill({ status: 200, json: {
        id: "user-1", organization_id: "org-1", email: "agent@example.test",
        full_name: "Demo Agent", role: "owner", is_active: true,
        organization: { id: "org-1", name: "Demo", slug: "demo" },
      } });
      return;
    }
    if (path === "/api/health/ready") {
      await route.fulfill({ status: 200, json: { status: "ready", checks: {} } });
      return;
    }
    if (path === "/api/inbox") {
      await route.fulfill({ status: 200, json: {
        items: [{
          ticket_id: ticket.id,
          conversation_id: conversation.id,
          subject: ticket.subject,
          status: ticket.status,
          priority: ticket.priority,
          customer: { id: ticket.customer_id, name: "Taylor Customer", email: "taylor@example.test" },
          assignee: ticket.assignee_id ? { id: ticket.assignee_id, name: "Demo Agent" } : null,
          latest_message: { preview: messages.at(-1)?.content ?? "", created_at: now, sender_type: messages.at(-1)?.sender_type ?? "customer" },
          unread_count: 1,
          updated_at: ticket.updated_at,
        }],
        limit: 30,
        next_cursor: null,
      } });
      return;
    }
    if (path === `/api/tickets/${ticket.id}/conversations` && request.method() === "GET") {
      await route.fulfill({ status: 200, json: [conversation] });
      return;
    }
    if (path === `/api/conversations/${conversation.id}/messages` && request.method() === "GET") {
      await route.fulfill({ status: 200, json: messages });
      return;
    }
    if (path === `/api/conversations/${conversation.id}/notes` && request.method() === "GET") {
      await route.fulfill({ status: 200, json: notes });
      return;
    }
    if (path === `/api/conversations/${conversation.id}/messages` && request.method() === "POST") {
      const body = request.postDataJSON() as { content: string };
      const message = {
        id: `agent-message-${nextMessageId++}`,
        conversation_id: conversation.id,
        sender_type: "agent",
        sender_user_id: "user-1",
        sender_name: "Demo Agent",
        content: body.content,
        content_type: "text",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      messages.push(message);
      await route.fulfill({ status: 201, json: message });
      return;
    }
    if (path === `/api/conversations/${conversation.id}/notes` && request.method() === "POST") {
      const body = request.postDataJSON() as { content: string };
      const note = {
        id: `internal-note-${nextMessageId++}`,
        conversation_id: conversation.id,
        sender_type: "internal_note",
        sender_user_id: "user-1",
        sender_name: "Demo Agent",
        content: body.content,
        content_type: "text",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      notes.push(note);
      await route.fulfill({ status: 201, json: note });
      return;
    }
    if (path === `/api/conversations/${conversation.id}/read`) {
      await route.fulfill({ status: 200, json: { conversation_id: conversation.id, last_read_at: now, last_read_message_id: messages.at(-1)?.id ?? null } });
      return;
    }
    if (path === `/api/tickets/${ticket.id}/assign-to-me`) {
      ticket.assignee_id = "user-1";
      ticket.assignee_name = "Demo Agent";
      ticket.updated_at = new Date().toISOString();
      await route.fulfill({ status: 200, json: ticket });
      return;
    }
    if (path === `/api/tickets/${ticket.id}` && request.method() === "PATCH") {
      const body = request.postDataJSON() as { status?: "open" | "resolved" };
      if (body.status) ticket.status = body.status;
      ticket.updated_at = new Date().toISOString();
      await route.fulfill({ status: 200, json: ticket });
      return;
    }
    if (path === `/api/tickets/${ticket.id}/activity`) {
      await route.fulfill({ status: 200, json: [] });
      return;
    }
    if (path === `/api/customers/${ticket.customer_id}/tickets`) {
      await route.fulfill({ status: 200, json: { items: [], total: 0, limit: 100, offset: 0 } });
      return;
    }
    if (path === "/api/users") {
      await route.fulfill({ status: 200, json: [{ id: "user-1", full_name: "Demo Agent", email: "agent@example.test", role: "owner", is_active: true }] });
      return;
    }
    await route.fulfill({ status: 200, json: [] });
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/dashboard/inbox");
  await page.getByRole("button", { name: /Taylor Customer.*Delivery question/ }).click();
  const thread = page.getByRole("region", { name: "Conversation thread" });
  await expect(thread.getByText("Can you check my delivery?")).toBeVisible();

  await page.getByLabel("Write a reply").fill("I’m checking this for you.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(thread.getByText("I’m checking this for you.")).toBeVisible();

  await page.getByRole("button", { name: "Internal note" }).click();
  await page.getByLabel("Write an internal note").fill("Check carrier portal before follow-up.");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(thread.getByRole("article", { name: "Internal note" })).toContainText("Check carrier portal before follow-up.");

  await page.getByRole("button", { name: "Assign ticket to me" }).click();
  await expect(page.getByText("Delivery question · Demo Agent")).toBeVisible();
  await page.getByLabel("Status", { exact: true }).selectOption("resolved");
  await expect(page.getByText("resolved", { exact: true }).first()).toBeVisible();
});
