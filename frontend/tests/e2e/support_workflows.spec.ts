import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function expectAccessible(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(result.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
}

test("register, create customer and ticket, assign an agent, and exchange a message", async ({ page, browser }) => {
  const unique = Date.now().toString();
  await page.goto("/register");
  const registerA11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(registerA11y.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
  await page.getByLabel("Organization name").fill(`Demo ${unique}`);
  await page.getByLabel("Organization slug").fill(`demo-${unique}`);
  await page.getByLabel("Your name").fill("Demo Owner");
  const ownerEmail = `owner-${unique}@example.com`;
  const ownerPassword = "demo-owner-long-password";
  const organizationSlug = `demo-${unique}`;
  await page.getByLabel("Work email").fill(ownerEmail);
  await page.getByLabel("Password").fill(ownerPassword);
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByRole("heading", { name: "Your workspace is awaiting review" })).toBeVisible();

  await page.goto("/login");
  await page.getByLabel("Organization slug").fill(organizationSlug);
  await page.getByLabel("Work email").fill(ownerEmail);
  await page.getByLabel("Password").fill(ownerPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator('p[role="alert"]')).toContainText("pending approval");
  expect((await page.context().cookies()).some((cookie) => cookie.name === "supportpilot_access")).toBe(false);

  const platformEmail = process.env.E2E_PLATFORM_OWNER_EMAIL;
  const platformPassword = process.env.E2E_PLATFORM_OWNER_PASSWORD;
  expect(platformEmail, "Set E2E_PLATFORM_OWNER_EMAIL to a bootstrapped platform owner").toBeTruthy();
  expect(platformPassword, "Set E2E_PLATFORM_OWNER_PASSWORD to a bootstrapped platform owner").toBeTruthy();
  const platformContext = await browser.newContext();
  const platform = await platformContext.newPage();
  await platform.goto("/platform/login");
  await platform.getByLabel("Platform owner email").fill(platformEmail!);
  await platform.getByLabel("Password").fill(platformPassword!);
  await platform.getByRole("button", { name: "Sign in to platform" }).click();
  await expect(platform.getByRole("heading", { name: "Tenant approvals" })).toBeVisible();
  await expectAccessible(platform);
  const tenantRow = platform.getByRole("row").filter({ hasText: organizationSlug });
  await tenantRow.getByRole("button", { name: "Approve" }).click();
  await expect(tenantRow).toHaveCount(0);
  await platformContext.close();

  await page.goto("/login");
  await page.getByLabel("Organization slug").fill(organizationSlug);
  await page.getByLabel("Work email").fill(ownerEmail);
  await page.getByLabel("Password").fill(ownerPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Good work starts here." })).toBeVisible();
  await page.getByRole("link", { name: "Operations" }).click();
  await expect(page.getByRole("heading", { name: "Operations" })).toBeVisible();
  await expect(page.getByText("PostgreSQL database", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Overall readiness" }).getByText("Core services ready")).toBeVisible();
  await expectAccessible(page);
  await page.getByRole("link", { name: "Security" }).click();
  await expect(page.getByRole("heading", { name: "Security", exact: true })).toBeVisible();
  await expect(page.getByText("Sign-in session", { exact: true })).toBeVisible();
  await expectAccessible(page);
  await page.getByRole("link", { name: "Overview" }).click();
  let shopifyConnected = false;
  await page.route("**/api/integrations/shopify/status", (route) => route.fulfill({ status: 200, json: shopifyConnected
    ? { configured: true, connected: true, shop_domain: "demo-store.myshopify.com", granted_scopes: ["read_customers", "read_orders"], connected_at: new Date().toISOString(), access_token_expires_at: new Date(Date.now() + 3600000).toISOString(), reconnect_required: false }
    : { configured: true, connected: false, shop_domain: null, granted_scopes: [], connected_at: null, access_token_expires_at: null, reconnect_required: false } }));

  await page.getByRole("link", { name: "Customers" }).click();
  await page.locator("details > summary").filter({ hasText: "Add a customer" }).click();
  await page.getByLabel("Full name").fill("Taylor Customer");
  await page.getByLabel("Email", { exact: true }).fill(`customer-${unique}@example.com`);
  await page.getByRole("button", { name: "Save customer" }).click();
  await expect(page.getByText("Taylor Customer")).toBeVisible();

  await page.getByRole("link", { name: "Tickets" }).click();
  await page.getByText("Create a ticket", { exact: true }).click();
  await page.getByLabel("Customer").selectOption({ index: 1 });
  await page.getByLabel("Subject").fill("Where is my order?");
  await page.getByRole("button", { name: "Create ticket" }).click();
  await page.getByRole("link", { name: "Where is my order?" }).click();
  await expect(page.getByRole("heading", { name: "Where is my order?" })).toBeVisible();
  await expectAccessible(page);
  const ticketId = new URL(page.url()).pathname.split("/").at(-1);
  expect(ticketId).toBeTruthy();
  await page.getByRole("link", { name: "Inbox" }).click();
  await page.getByRole("button", { name: /Taylor Customer.*Where is my order\?/ }).click();
  await page.getByRole("button", { name: "Assign to me" }).click();
  await expect(page.getByRole("button", { name: "Assign to me" })).toHaveCount(0);
  await page.getByRole("button", { name: "Unread", exact: true }).click();
  await expect(page.getByText("No tickets match")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Select a ticket" })).toBeVisible();
  await page.getByRole("button", { name: "All", exact: true }).click();
  await page.getByRole("button", { name: /Taylor Customer.*Where is my order\?/ }).click();
  await page.getByRole("link", { name: "Tickets" }).click();
  await page.getByRole("link", { name: "Where is my order?" }).click();
  await page.getByRole("button", { name: "Search workspace" }).click();
  await page.getByLabel("Search tickets, customers, or documents").fill("Where is my order");
  await expect(page.getByRole("link", { name: /Where is my order\?/ })).toBeVisible();
  await page.getByRole("link", { name: /Where is my order\?/ }).click();
  await expect(page.getByRole("heading", { name: "Where is my order?" })).toBeVisible();

  await page.getByRole("link", { name: "Settings & team" }).click();
  await expect(page.getByRole("button", { name: "Connect Shopify" })).toBeVisible();
  await expectAccessible(page);
  await page.route("https://demo-store.myshopify.com/admin/oauth/authorize**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "Shopify authorization screen mock" }));
  await page.getByLabel("Shopify store domain").fill("demo-store.myshopify.com");
  await page.getByRole("button", { name: "Connect Shopify" }).click();
  await page.waitForURL("https://demo-store.myshopify.com/admin/oauth/authorize**");
  const authorization = new URL(page.url());
  expect(authorization.searchParams.get("scope")).toBe("read_orders,read_customers");
  expect(authorization.searchParams.get("redirect_uri")).toBe("https://supportpilot.example/api/integrations/shopify/callback");
  expect(authorization.searchParams.get("state")).toBeTruthy();
  shopifyConnected = true;
  await page.goto("/dashboard/settings");
  await expect(page.getByText("Connected · demo-store.myshopify.com")).toBeVisible();
  await expectAccessible(page);
  await page.getByLabel("Work email").fill(`agent-${unique}@example.com`);
  await page.getByRole("button", { name: "Create invite link" }).click();
  const inviteLink = (await page.locator("p.break-all").textContent())?.trim();
  expect(inviteLink).toContain("/invite/");

  const teammate = await browser.newPage();
  await teammate.goto(inviteLink!);
  await teammate.getByLabel("Full name").fill("Demo Agent");
  await teammate.getByLabel("Create a password").fill("demo-agent-long-password");
  await teammate.getByRole("button", { name: "Join workspace" }).click();
  await expect(teammate.getByRole("heading", { name: "Good work starts here." })).toBeVisible();

  await page.getByRole("link", { name: "Tickets" }).click();
  await page.getByRole("link", { name: "Where is my order?" }).click();
  await page.getByLabel("Assignee").selectOption({ label: "Demo Agent · agent" });
  await page.getByRole("button", { name: "Start conversation" }).click();
  await page.getByLabel("Write a message").fill("I am checking on this for you.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByText("I am checking on this for you.")).toBeVisible();
  const secondConversationStatus = await page.evaluate(async (id) => {
    const response = await fetch(`/api/tickets/${id}/conversations`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ channel: "email" }),
    });
    return response.status;
  }, ticketId);
  expect(secondConversationStatus).toBe(201);
  await page.reload();
  await expect(page.getByText("Choose a conversation", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Conversation 1/ }).click();
  await expect(page.getByText("I am checking on this for you.")).toBeVisible();
  await page.getByRole("link", { name: "Inbox" }).click();
  await page.getByRole("button", { name: /Taylor Customer.*Where is my order\?/ }).click();
  await expect(page.getByText("Choose a conversation", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Conversation 1/ }).click();
  await expect(page.getByText("I am checking on this for you.")).toBeVisible();
  await page.getByRole("button", { name: "Internal note" }).click();
  await page.getByLabel("Write an internal note").fill("Check the carrier status before the next reply.");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByText("Check the carrier status before the next reply.")).toBeVisible();
  await expect(page.getByText(/Internal note ·/)).toBeVisible();
  await page.getByRole("button", { name: "Reply", exact: true }).click();
  const draftExecutionId = "f0c6a074-d911-4a83-9b78-6c0ad0d54e90";
  const draftExecution = {
    id: draftExecutionId,
    kind: "reply_draft",
    status: "succeeded",
    safe_summary: "Reply draft generated using 1 knowledge source(s).",
    draft: "I am checking your order and will update you shortly.",
    citations: [{ document_id: "a6b6b3aa-2337-494d-9cf6-fd82e15fb35c", document_name: "support-guide.txt", chunk_index: 0, excerpt: "When an order needs review, a support agent follows up with the customer." }],
    tool_outcomes: [{ tool: "tenant_knowledge_search", status: "completed", result_count: 1 }],
    usage: { prompt_tokens: 20, completion_tokens: 12, total_tokens: 32 },
    model_name: "test-model",
    error_code: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
  };
  await page.getByLabel("Shopify order number for AI draft").fill("1001");
  await page.route("**/api/ai/reply-drafts", (route) => {
    expect(route.request().postDataJSON()).toMatchObject({
      conversation_id: expect.any(String),
      shopify_order_number: "1001",
    });
    return route.fulfill({ status: 202, json: { ...draftExecution, status: "queued", draft: null, citations: [], completed_at: null } });
  });
  await page.route(`**/api/ai/executions/${draftExecutionId}`, (route) => route.fulfill({ status: 200, json: draftExecution }));
  const customerMessageWrites: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/conversations\/[^/]+\/messages$/.test(new URL(request.url()).pathname)) customerMessageWrites.push(request.url());
  });
  await page.getByRole("button", { name: "Draft with AI" }).click();
  await expect(page.getByText("AI draft · review before sending")).toBeVisible();
  await expect(page.getByText("support-guide.txt · section 1")).toBeVisible();
  expect(customerMessageWrites).toHaveLength(0);
  await page.getByRole("button", { name: "Add to reply" }).click();
  await expect(page.getByLabel("Write a reply")).toHaveValue(draftExecution.draft);
  expect(customerMessageWrites).toHaveLength(0);
  await expect(page.getByRole("complementary", { name: "Customer context" })).toBeVisible();
  await expect(page.getByText("Recent tickets", { exact: true })).toBeVisible();
  const inboxA11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(inboxA11y.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open ticket and customer details" }).click();
  const detailsDialog = page.getByRole("dialog", { name: "Ticket and customer details" });
  await expect(detailsDialog).toBeVisible();
  await expect(detailsDialog.getByLabel("Status")).toBeEnabled();
  const mobileInboxA11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(mobileInboxA11y.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(detailsDialog).toBeHidden();
  await page.setViewportSize({ width: 1280, height: 800 });

  const playgroundExecutionId = "a22217a4-f3a9-4a55-8d41-810ad80a32a0";
  const playgroundExecution = { ...draftExecution, id: playgroundExecutionId, kind: "playground", safe_summary: "Playground answer generated using 1 knowledge source(s).", draft: "Unused products may be returned within thirty days with proof of purchase." };
  await page.route("**/api/ai/playground", (route) => route.fulfill({ status: 202, json: { ...playgroundExecution, status: "queued", draft: null, citations: [], completed_at: null } }));
  await page.route(`**/api/ai/executions/${playgroundExecutionId}`, (route) => route.fulfill({ status: 200, json: playgroundExecution }));
  await page.getByRole("link", { name: "AI Playground" }).click();
  await page.getByLabel("Question").fill("What is the return policy?");
  await page.getByRole("button", { name: "Generate answer" }).click();
  await expect(page.getByText(playgroundExecution.draft)).toBeVisible();
  const playgroundA11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(playgroundA11y.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);

  await page.getByRole("link", { name: "Analytics" }).click();
  await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
  await expect(page.getByText("AI requests", { exact: true })).toBeVisible();
  await expect(page.getByText("No AI activity in this date range.")).toBeVisible();
  const analyticsA11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(analyticsA11y.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);

  await page.getByRole("link", { name: "Knowledge" }).click();
  await expectAccessible(page);
  await page.getByLabel("Choose a PDF, text, or Markdown document").setInputFiles({
    name: "returns-policy.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Customers can return unused products within thirty days with proof of purchase."),
  });
  const documentLink = page.getByRole("link", { name: "returns-policy.txt" });
  await expect(documentLink).toBeVisible();
  await expect(page.getByText("ready", { exact: true })).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Search documents").fill("thirty days");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText(/returns-policy\.txt · section 1/)).toBeVisible();
  await documentLink.click();
  await expect(page.getByRole("heading", { name: "returns-policy.txt" })).toBeVisible();
  await expectAccessible(page);
  await expect(page.getByRole("heading", { name: "Processing history" })).toBeVisible();
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Source citations" })).toBeVisible();
  await page.getByRole("link", { name: "Document library" }).click();
  await page.getByRole("button", { name: "Reprocess returns-policy.txt" }).click();
  await documentLink.click();
  await expect.poll(() => page.getByText("succeeded", { exact: true }).count(), { timeout: 30_000 }).toBe(2);
  await page.getByRole("link", { name: "Document library" }).click();
  await page.getByRole("button", { name: "Delete returns-policy.txt" }).click();
  await expect(documentLink).toHaveCount(0);
  await expect(page.getByText("No documents yet")).toBeVisible();

  await page.route("**/api/integrations/shopify/orders?*", async (route) => {
    const requestUrl = new URL(route.request().url());
    expect(requestUrl.searchParams.get("customer_email")).toBe("morgan@example.test");
    expect(requestUrl.searchParams.get("order_number")).toBe("1001");
    await route.fulfill({ status: 200, json: {
      customer: { display_name: "Morgan Buyer", email: "morgan@example.test", verified_by: "order_number_and_email" },
      matched_order: { id: "gid://shopify/Order/1001", order_number: "#1001", created_at: new Date().toISOString(), financial_status: "PAID", fulfillment_status: "FULFILLED", total_amount: "42.50", currency: "USD", tracking: [{ company: "UPS", number: "1Z999", url: "https://tracking.example/1Z999" }] },
      recent_orders: [{ id: "gid://shopify/Order/1001", order_number: "#1001", created_at: new Date().toISOString(), financial_status: "PAID", fulfillment_status: "FULFILLED", total_amount: "42.50", currency: "USD", tracking: [{ company: "UPS", number: "1Z999", url: "https://tracking.example/1Z999" }] }],
      has_next_page: false,
      next_cursor: null,
    } });
  });
  await page.getByRole("link", { name: "Shopify orders" }).click();
  await page.getByLabel("Customer email").fill("morgan@example.test");
  await page.getByLabel("Shopify order number").fill("1001");
  await page.getByRole("button", { name: "Verify and find orders" }).click();
  await expect(page.getByText("Verified customer order history")).toBeVisible();
  await expect(page.getByText("UPS · 1Z999")).toBeVisible();
  const orderA11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(orderA11y.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
});

test("rejected tenant remains blocked from workspace login", async ({ page, browser }) => {
  const unique = Date.now().toString();
  const email = `rejected-${unique}@example.com`;
  const slug = `rejected-${unique}`;
  const password = "demo-owner-long-password";
  await page.goto("/register");
  await page.getByLabel("Organization name").fill(`Rejected ${unique}`);
  await page.getByLabel("Organization slug").fill(slug);
  await page.getByLabel("Your name").fill("Rejected Owner");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByRole("heading", { name: "Your workspace is awaiting review" })).toBeVisible();

  const platformContext = await browser.newContext();
  const platform = await platformContext.newPage();
  await platform.goto("/platform/login");
  await platform.getByLabel("Platform owner email").fill(process.env.E2E_PLATFORM_OWNER_EMAIL!);
  await platform.getByLabel("Password").fill(process.env.E2E_PLATFORM_OWNER_PASSWORD!);
  await platform.getByRole("button", { name: "Sign in to platform" }).click();
  await expect(platform.getByRole("heading", { name: "Tenant approvals" })).toBeVisible();
  const tenantRow = platform.getByRole("row").filter({ hasText: slug });
  await expect(tenantRow).toBeVisible();
  await tenantRow.getByRole("button", { name: "Reject" }).click();
  await platformContext.close();

  await page.goto("/login");
  await page.getByLabel("Organization slug").fill(slug);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator('p[role="alert"]')).toContainText("rejected");
  expect((await page.context().cookies()).some((cookie) => cookie.name === "supportpilot_access")).toBe(false);
});

test("BFF exposes real readiness and rejects cross-origin mutations with Problem Details", async ({ page }) => {
  const readiness = await page.request.get("/api/health/ready");
  expect(readiness.status()).toBe(200);
  expect((await readiness.json()).status).toBe("ready");

  const response = await page.request.post("/api/auth/logout", {
    headers: { origin: "https://untrusted.example" },
  });
  expect(response.status()).toBe(403);
  expect(response.headers()["content-type"]).toContain("application/problem+json");
  expect((await response.json()).code).toBe("cross_origin_rejected");
});

test("public landing, features, and pricing pages describe the current product accessibly", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /A calmer place to support your customers/ })).toBeVisible();
  await expect(page.getByText("Workspace registration is reviewed before access is enabled.")).toBeVisible();
  const landingA11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(landingA11y.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);

  await page.getByRole("link", { name: "Features" }).first().click();
  await expect(page.getByRole("heading", { name: "A complete view of the support conversation" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Shopify order lookup" })).toBeVisible();
  const featuresA11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(featuresA11y.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);

  await page.getByRole("link", { name: "Pricing" }).first().click();
  await expect(page.getByRole("heading", { name: "Pricing information" })).toBeVisible();
  await expect(page.getByText(/Public pricing and plan limits aren’t published yet/)).toBeVisible();
  const pricingA11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(pricingA11y.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
});
