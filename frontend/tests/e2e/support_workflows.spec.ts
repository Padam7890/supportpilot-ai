import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

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
  await expect(page.getByRole("alert")).toContainText("pending approval");
  expect((await page.context().cookies()).some((cookie) => cookie.name === "supportpilot_access")).toBe(false);

  const platformEmail = process.env.E2E_PLATFORM_OWNER_EMAIL;
  const platformPassword = process.env.E2E_PLATFORM_OWNER_PASSWORD;
  expect(platformEmail, "Set E2E_PLATFORM_OWNER_EMAIL to a bootstrapped platform owner").toBeTruthy();
  expect(platformPassword, "Set E2E_PLATFORM_OWNER_PASSWORD to a bootstrapped platform owner").toBeTruthy();
  const platform = await browser.newPage();
  await platform.goto("/platform/login");
  await platform.getByLabel("Platform owner email").fill(platformEmail!);
  await platform.getByLabel("Password").fill(platformPassword!);
  await platform.getByRole("button", { name: "Sign in to platform" }).click();
  await expect(platform.getByRole("heading", { name: "Tenant approvals" })).toBeVisible();
  const tenantRow = platform.getByRole("row").filter({ hasText: organizationSlug });
  await tenantRow.getByRole("button", { name: "Approve" }).click();
  await expect(tenantRow).toHaveCount(0);
  await platform.close();

  await page.goto("/login");
  await page.getByLabel("Organization slug").fill(organizationSlug);
  await page.getByLabel("Work email").fill(ownerEmail);
  await page.getByLabel("Password").fill(ownerPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Good work starts here." })).toBeVisible();

  await page.getByRole("link", { name: "Customers" }).click();
  await page.getByText("Add a customer", { exact: true }).click();
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

  await page.getByRole("link", { name: "Settings & team" }).click();
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
  await page.getByLabel("Assignee").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Start conversation" }).click();
  await page.getByLabel("Write a message").fill("I am checking on this for you.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByText("I am checking on this for you.")).toBeVisible();
  await page.getByRole("link", { name: "Inbox" }).click();
  await page.getByRole("button", { name: /Taylor Customer.*Where is my order\?/ }).click();
  await expect(page.getByText("I am checking on this for you.")).toBeVisible();
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

  await page.getByRole("link", { name: "Knowledge" }).click();
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

  const platform = await browser.newPage();
  await platform.goto("/platform/login");
  await platform.getByLabel("Platform owner email").fill(process.env.E2E_PLATFORM_OWNER_EMAIL!);
  await platform.getByLabel("Password").fill(process.env.E2E_PLATFORM_OWNER_PASSWORD!);
  await platform.getByRole("button", { name: "Sign in to platform" }).click();
  const tenantRow = platform.getByRole("row").filter({ hasText: slug });
  await tenantRow.getByRole("button", { name: "Reject" }).click();
  await platform.close();

  await page.goto("/login");
  await page.getByLabel("Organization slug").fill(slug);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("rejected");
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
