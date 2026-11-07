import { expect, test } from "@playwright/test";

const baseUrl = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";
const accessToken = process.env.E2E_ACCESS_TOKEN;

test("knowledge base and bot management persist through the live API and worker", async ({ page }) => {
  test.skip(!accessToken, "Set E2E_ACCESS_TOKEN to run against a live local FastAPI/worker stack.");
  if (!accessToken) return;

  await page.context().addCookies([{
    name: "supportpilot_access",
    value: accessToken,
    url: baseUrl,
    httpOnly: true,
    sameSite: "Lax",
  }]);

  const baseName = `Service returns ${crypto.randomUUID().slice(0, 8)}`;
  const documentName = `service-policy-${crypto.randomUUID().slice(0, 8)}.txt`;
  const botName = `Service returns bot ${crypto.randomUUID().slice(0, 8)}`;

  await page.goto("/dashboard/knowledge");
  await page.getByLabel("New knowledge base name").fill(baseName);
  await page.getByRole("button", { name: "Create base" }).click();
  await expect(page.getByRole("button", { name: baseName, exact: true })).toBeVisible();

  await page.getByLabel("Choose a PDF, text, or Markdown document").setInputFiles({
    name: documentName,
    mimeType: "text/plain",
    buffer: Buffer.from("Unused products may be returned within 30 days with proof of purchase."),
  });
  await expect(page.getByRole("link", { name: documentName })).toBeVisible();
  await expect(page.getByText("ready", { exact: true })).toBeVisible({ timeout: 30_000 });

  await page.goto("/dashboard/ai/agents");
  await page.getByRole("button", { name: "New bot" }).click();
  await page.getByLabel("Bot name").fill(botName);
  await page.getByLabel("System instructions").fill("Answer from the assigned returns policy only.");
  await page.getByLabel(baseName).check();
  await page.getByRole("button", { name: "Create bot" }).click();
  await expect(page.getByRole("heading", { name: "Bot configuration" })).toBeVisible();
  await expect(page.getByLabel(baseName)).toBeChecked();

  const persisted = await page.evaluate(async (expectedName) => {
    const response = await fetch("/api/ai/agents?limit=100&offset=0", { cache: "no-store" });
    if (!response.ok) throw new Error(`AI bot API returned HTTP ${response.status}`);
    const result = await response.json() as { items: Array<{ name: string; knowledge_base_ids: string[] }> };
    return result.items.find((agent) => agent.name === expectedName) ?? null;
  }, botName);
  expect(persisted).not.toBeNull();
  expect(persisted?.knowledge_base_ids).toHaveLength(1);
});
