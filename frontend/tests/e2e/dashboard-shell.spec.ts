import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function mockWorkspaceApis(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      await route.fulfill({
        status: 200,
        json: {
          id: "user-1",
          organization_id: "org-1",
          email: "agent@example.test",
          full_name: "Demo Agent",
          role: "owner",
          is_active: true,
          organization: { id: "org-1", name: "SupportPilot Demo", slug: "supportpilot-demo" },
        },
      });
      return;
    }
    if (url.pathname === "/api/health/ready") {
      await route.fulfill({ status: 200, json: { status: "ready", checks: { database: "connected", redis: "connected" } } });
      return;
    }
    if (url.pathname === "/api/health/worker") {
      await route.fulfill({ status: 200, json: { status: "active", active_workers: 1, checked_at: new Date().toISOString() } });
      return;
    }
    if (url.pathname === "/api/inbox") {
      await route.fulfill({ status: 200, json: { items: [], limit: 30, next_cursor: null } });
      return;
    }
    await route.fulfill({ status: 200, json: {} });
  });
}

async function mockInboxFailure(page: Page, failingPath: string) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      await route.fulfill({
        status: 200,
        json: {
          id: "user-1",
          organization_id: "org-1",
          email: "agent@example.test",
          full_name: "Demo Agent",
          role: "owner",
          is_active: true,
          organization: { id: "org-1", name: "SupportPilot Demo", slug: "supportpilot-demo" },
        },
      });
      return;
    }
    if (url.pathname === "/api/health/ready") {
      await route.fulfill({ status: 200, json: { status: "ready", checks: {} } });
      return;
    }
    if (url.pathname === "/api/health/worker") {
      await route.fulfill({ status: 200, json: { status: "active", active_workers: 1, checked_at: new Date().toISOString() } });
      return;
    }
    if (url.pathname === "/api/inbox") {
      await route.fulfill({
        status: 200,
        json: {
          items: [{
            ticket_id: "ticket-1",
            conversation_id: "conversation-1",
            subject: "Where is my order?",
            status: "open",
            priority: "normal",
            customer: { id: "customer-1", name: "Taylor Customer", email: null },
            assignee: null,
            latest_message: { preview: "Can you check?", created_at: new Date().toISOString(), sender_type: "customer" },
            unread_count: 1,
            updated_at: new Date().toISOString(),
          }],
          limit: 30,
          next_cursor: null,
        },
      });
      return;
    }
    if (url.pathname === "/api/integrations/shopify/status") {
      await route.fulfill({ status: 200, json: { connected: false, shop_domain: null, granted_scopes: [] } });
      return;
    }
    if (url.pathname === "/api/commerce/actions") {
      await route.fulfill({ status: 200, json: { items: [], total: 0, limit: 25, offset: 0 } });
      return;
    }
    if (url.pathname === "/api/customers/customer-1/tickets") {
      await route.fulfill({ status: 200, json: { items: [], total: 0, limit: 20, offset: 0 } });
      return;
    }
    if (url.pathname === "/api/tickets/ticket-1/activity") {
      await route.fulfill({ status: 200, json: [] });
      return;
    }
    if (url.pathname === failingPath) {
      await route.fulfill({
        status: 500,
        headers: {
          "content-type": "application/problem+json",
          "x-correlation-id": "inbox-request-123",
        },
        body: JSON.stringify({
          title: "Internal Server Error",
          status: 500,
          detail: "An unexpected server error occurred",
          code: "internal_error",
        }),
      });
      return;
    }
    if (url.pathname === "/api/tickets/ticket-1/conversations") {
      await route.fulfill({
        status: 200,
        json: [{
          id: "conversation-1",
          ticket_id: "ticket-1",
          channel: "web",
          status: "active",
          ai_mode: "human",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }],
      });
      return;
    }
    await route.fulfill({ status: 200, json: [] });
  });
}

test("desktop sidebar keeps grouped navigation and collapse state across routes", async ({ page }) => {
  await mockWorkspaceApis(page);
  await page.setViewportSize({ width: 1365, height: 900 });
  await page.goto("/dashboard/inbox");

  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await expect(navigation.getByRole("group", { name: "Workspace" })).toBeVisible();
  await expect(navigation.getByRole("group", { name: "AI Studio" })).toBeVisible();
  await expect(navigation.getByRole("group", { name: "Connections" })).toBeVisible();
  await expect(navigation.getByRole("group", { name: "Administration" })).toBeVisible();
  await expect(navigation.getByRole("link", { name: "Inbox" })).toHaveAttribute("aria-current", "page");

  await page.getByRole("complementary").getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(navigation.getByRole("link", { name: "Inbox" })).toHaveAttribute("title", "Inbox");
  await navigation.getByRole("link", { name: "Overview" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("complementary").getByRole("button", { name: "Expand sidebar" })).toBeVisible();
  await navigation.getByRole("link", { name: "Inbox" }).click();
  await expect(page).toHaveURL(/\/dashboard\/inbox$/);
  await expect(navigation.getByRole("link", { name: "Inbox" })).toHaveAttribute("aria-current", "page");
  await expect(page).toHaveTitle("SupportPilot AI");

  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
});

test("mobile sidebar opens as a drawer and closes after navigation", async ({ page }) => {
  await mockWorkspaceApis(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard/inbox");
  await page.getByRole("button", { name: "Open navigation" }).click();

  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await expect(navigation.getByRole("link", { name: "Widget" })).toBeVisible();
  await navigation.getByRole("link", { name: "Widget" }).click();
  await expect(page).toHaveURL(/\/dashboard\/widget$/);
  await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
});

test("conversation load errors show their backend correlation reference", async ({ page }) => {
  await mockInboxFailure(page, "/api/tickets/ticket-1/conversations");
  await page.goto("/dashboard/inbox");
  await page.getByRole("button", { name: /Taylor Customer.*Where is my order\?/ }).click();

  const error = page.getByRole("alert").filter({ hasText: "Could not load this ticket’s conversations" });
  await expect(error).toContainText("Reference: inbox-request-123");
});

test("a new second conversation requires an explicit choice before showing a transcript", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-11-06T12:00:00Z") });
  let conversationListRequests = 0;
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      await route.fulfill({ status: 200, json: { id: "user-1", email: "agent@example.test", full_name: "Demo Agent", role: "owner", is_active: true, organization: { id: "org-1", name: "Demo", slug: "demo" } } });
      return;
    }
    if (url.pathname === "/api/health/ready") {
      await route.fulfill({ status: 200, json: { status: "ready", checks: {} } });
      return;
    }
    if (url.pathname === "/api/inbox") {
      await route.fulfill({ status: 200, json: { items: [{ ticket_id: "ticket-1", conversation_id: "conversation-1", subject: "Order question", status: "open", priority: "normal", customer: { id: "customer-1", name: "Taylor Customer", email: null }, assignee: null, latest_message: { preview: "Can you help?", created_at: "2026-11-06T12:00:00Z", sender_type: "customer" }, unread_count: 1, updated_at: "2026-11-06T12:00:00Z" }], limit: 30, next_cursor: null } });
      return;
    }
    if (url.pathname === "/api/tickets/ticket-1/conversations") {
      conversationListRequests += 1;
      const conversation = { id: "conversation-1", ticket_id: "ticket-1", channel: "web", status: "active", ai_mode: "human", created_at: "2026-11-06T12:00:00Z", updated_at: "2026-11-06T12:00:00Z" };
      const items = conversationListRequests < 2 ? [conversation] : [conversation, { ...conversation, id: "conversation-2", channel: "email" }];
      await route.fulfill({ status: 200, json: items });
      return;
    }
    if (url.pathname === "/api/conversations/conversation-1/messages" || url.pathname === "/api/conversations/conversation-1/notes") {
      await route.fulfill({ status: 200, json: [] });
      return;
    }
    if (url.pathname === "/api/integrations/shopify/status") {
      await route.fulfill({ status: 200, json: { connected: false, shop_domain: null, granted_scopes: [] } });
      return;
    }
    await route.fulfill({ status: 200, json: [] });
  });

  await page.goto("/dashboard/inbox");
  await page.getByRole("button", { name: /Taylor Customer.*Order question/ }).click();
  await expect(page.getByLabel("Write a reply")).toBeVisible();
  await page.clock.fastForward(10_000);
  await expect(page.getByText("This ticket has separate conversation histories. Select one to view its messages.")).toBeVisible();
  await expect(page.getByLabel("Choose conversation")).toHaveValue("");
  await expect(page.getByLabel("Write a reply")).toHaveCount(0);
  await page.getByLabel("Choose conversation").selectOption("conversation-2");
  await expect(page.getByLabel("Write a reply")).toBeVisible();
  expect(conversationListRequests).toBeGreaterThanOrEqual(2);
});

test("message load errors show their backend correlation reference", async ({ page }) => {
  await mockInboxFailure(page, "/api/conversations/conversation-1/messages");
  await page.goto("/dashboard/inbox");
  await page.getByRole("button", { name: /Taylor Customer.*Where is my order\?/ }).click();

  const error = page.getByRole("alert").filter({ hasText: "Could not load messages" });
  await expect(error).toContainText("Reference: inbox-request-123");
});

test("an agent can start a conversation for a ticket without a thread from the inbox", async ({ page }) => {
  await mockInboxFailure(page, "/api/no-failure");
  await page.route("**/api/tickets/ticket-1/conversations", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 201,
        json: {
          id: "conversation-new",
          ticket_id: "ticket-1",
          channel: "web",
          status: "active",
          ai_mode: "human",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      });
      return;
    }
    await route.fulfill({ status: 200, json: [] });
  });
  await page.goto("/dashboard/inbox");
  await page.getByRole("button", { name: /Taylor Customer.*Where is my order\?/ }).click();
  await expect(page.getByText("No conversation yet")).toBeVisible();
  await page.getByRole("button", { name: "Start conversation" }).click();
  await expect(page.getByLabel("Write a reply")).toBeVisible();
});
