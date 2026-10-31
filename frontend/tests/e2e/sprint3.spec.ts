import { expect, test } from "@playwright/test";

test("register, create customer and ticket, assign an agent, and exchange a message", async ({ page, browser }) => {
  const unique = Date.now().toString();
  await page.goto("/register");
  await page.getByLabel("Organization name").fill(`Demo ${unique}`);
  await page.getByLabel("Organization slug").fill(`demo-${unique}`);
  await page.getByLabel("Your name").fill("Demo Owner");
  await page.getByLabel("Work email").fill(`owner-${unique}@example.test`);
  await page.getByLabel("Password").fill("demo-owner-long-password");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByRole("heading", { name: "Good work starts here." })).toBeVisible();

  await page.getByRole("link", { name: "Customers" }).click();
  await page.getByText("Add a customer", { exact: true }).click();
  await page.getByLabel("Full name").fill("Taylor Customer");
  await page.getByLabel("Email", { exact: true }).fill(`customer-${unique}@example.test`);
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
  await page.getByLabel("Work email").fill(`agent-${unique}@example.test`);
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
});
