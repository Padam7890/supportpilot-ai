import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("owner creates, previews, and saves a customer-message workflow", async ({ page }) => {
  let workflows: Array<Record<string, unknown>> = [];
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    if (url.pathname === "/api/auth/me") {
      await route.fulfill({ status: 200, json: { id: "owner-1", email: "owner@example.com", full_name: "Workspace Owner", role: "owner", is_active: true, organization: { id: "org-1", name: "Demo Workspace", slug: "demo" } } });
      return;
    }
    if (url.pathname === "/api/health/ready") {
      await route.fulfill({ status: 200, json: { status: "ready", checks: { database: "connected" } } });
      return;
    }
    if (url.pathname === "/api/health/worker") {
      await route.fulfill({ status: 200, json: { status: "active", active_workers: 1, checked_at: new Date().toISOString() } });
      return;
    }
    if (url.pathname === "/api/users" && method === "GET") {
      await route.fulfill({ status: 200, json: [] });
      return;
    }
    if (url.pathname === "/api/automations/metrics") {
      await route.fulfill({ status: 200, json: { window_start: "2026-01-01T00:00:00Z", window_end: "2026-01-31T00:00:00Z", total: 0, queued: 0, running: 0, succeeded: 0, failed: 0, average_duration_ms: null } });
      return;
    }
    if (url.pathname === "/api/automations/preview" && method === "POST") {
      const body = route.request().postDataJSON() as { definition: { conditions: Array<{ value: string }> }; sample_message: string };
      const matched = body.definition.conditions.every((condition) => body.sample_message.toLowerCase().includes(condition.value.toLowerCase()));
      await route.fulfill({ status: 200, json: { matches: matched, condition_mode: "all", conditions: body.definition.conditions.map((condition) => ({ kind: "contains_keyword", label: `Message contains ${condition.value}`, matched })), planned_actions: matched ? [{ kind: "set_priority", summary: "Set priority to high", outcome: "would_run" }] : [], steps: [] } });
      return;
    }
    if (url.pathname === "/api/automations" && method === "GET") {
      await route.fulfill({ status: 200, json: workflows });
      return;
    }
    if (url.pathname === "/api/automations" && method === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      workflows = [{ ...body, id: "workflow-1", status: "draft", published_version: null, draft_version: 1, has_unpublished_changes: false }];
      await route.fulfill({ status: 201, json: workflows[0] });
      return;
    }
    await route.fulfill({ status: 200, json: {} });
  });

  await page.setViewportSize({ width: 1365, height: 900 });
  await page.goto("/dashboard/automations");
  await expect(page.getByRole("heading", { name: "Workflows", level: 1 })).toBeVisible();
  await page.getByRole("link", { name: "New workflow" }).click();
  const canvasBounds = await page.getByRole("region", { name: "Scrollable workflow canvas" }).boundingBox();
  const inspectorBounds = await page.getByRole("complementary", { name: "Inspector" }).boundingBox();
  if (!canvasBounds || !inspectorBounds) throw new Error("Workflow editor panes must be visible");
  expect(inspectorBounds.y).toBeGreaterThan(canvasBounds.y + canvasBounds.height - 8);
  await page.getByLabel("Workflow name").fill("Refund triage");
  await page.locator('[data-library-item="cond-keyword"]').getByRole("button", { name: "Add" }).click();
  await page.getByLabel("Condition 1 · message contains").fill("refund");
  await page.getByRole("button", { name: "Test", exact: true }).click();
  await page.getByLabel("Sample customer message").fill("I need help with a refund");
  await page.getByRole("button", { name: "Run test" }).click();
  await expect(page.getByText("Workflow would match")).toBeVisible();
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page).toHaveURL(/edit=workflow-1/);
  await expect(page.getByText("Draft saved.")).toBeVisible();
  expect(pageErrors).toEqual([]);

  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
});
