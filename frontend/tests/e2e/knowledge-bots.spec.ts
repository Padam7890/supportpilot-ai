import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

type BaseRecord = {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  status: "active" | "archived";
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

const now = "2026-11-06T00:00:00Z";
const organizationId = "00000000-0000-0000-0000-000000000001";
const defaultBase: BaseRecord = {
  id: "00000000-0000-0000-0000-000000000002",
  organization_id: organizationId,
  name: "General",
  description: "Default knowledge base",
  status: "active",
  is_default: true,
  created_at: now,
  updated_at: now,
};

test("creates a knowledge base, assigns it to a bot, and shows a cited bot answer", async ({ page }) => {
  let bases: BaseRecord[] = [defaultBase];
  let agents: Array<Record<string, unknown>> = [];
  let uploadedDocument: Record<string, unknown> | undefined;
  let submittedPlaygroundRequest: Record<string, unknown> | undefined;
  const agentId = "550e8400-e29b-41d4-a716-446655440003";
  const documentId = "00000000-0000-0000-0000-000000000004";
  const executionId = "00000000-0000-0000-0000-000000000005";

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (url.pathname === "/api/auth/me") {
      await route.fulfill({ status: 200, json: { id: "owner-1", email: "owner@example.com", full_name: "Workspace Owner", role: "owner", is_active: true, organization: { id: organizationId, name: "Demo Workspace", slug: "demo" } } });
      return;
    }
    if (url.pathname === "/api/health/ready") {
      await route.fulfill({ status: 200, json: { status: "ready", checks: { database: "connected" } } });
      return;
    }
    if (url.pathname === "/api/knowledge/bases" && method === "GET") {
      await route.fulfill({ status: 200, json: { items: bases, total: bases.length, limit: 100, offset: 0 } });
      return;
    }
    if (url.pathname === "/api/knowledge/bases" && method === "POST") {
      const body = route.request().postDataJSON() as { name: string; description: string | null };
      const created: BaseRecord = { ...defaultBase, id: "00000000-0000-0000-0000-000000000006", name: body.name, description: body.description, is_default: false };
      bases = [...bases, created];
      await route.fulfill({ status: 201, json: created });
      return;
    }
    if (url.pathname === "/api/knowledge/bases/00000000-0000-0000-0000-000000000006" && method === "PUT") {
      const body = route.request().postDataJSON() as { name: string; description: string | null };
      bases = bases.map((base) => base.id === "00000000-0000-0000-0000-000000000006" ? { ...base, ...body } : base);
      await route.fulfill({ status: 200, json: bases.find((base) => base.id === "00000000-0000-0000-0000-000000000006") });
      return;
    }
    if (url.pathname === "/api/knowledge/documents" && method === "GET") {
      const items = uploadedDocument ? [uploadedDocument] : [];
      await route.fulfill({ status: 200, json: { items, total: items.length, limit: 50, offset: 0 } });
      return;
    }
    if (url.pathname === "/api/knowledge/documents" && method === "POST") {
      expect(url.searchParams.get("knowledge_base_id")).toBe("00000000-0000-0000-0000-000000000006");
      uploadedDocument = {
        id: documentId,
        organization_id: organizationId,
        knowledge_base_id: "00000000-0000-0000-0000-000000000006",
        name: url.searchParams.get("name") ?? "returns-policy.txt",
        content_type: "text/plain",
        size_bytes: 75,
        status: "ready",
        uploaded_by_user_id: "owner-1",
        deleted_at: null,
        created_at: now,
        updated_at: now,
        jobs: [],
      };
      await route.fulfill({ status: 202, json: uploadedDocument });
      return;
    }
    if (url.pathname === "/api/ai/agents" && method === "GET") {
      await route.fulfill({ status: 200, json: { items: agents, total: agents.length, limit: 100, offset: 0 } });
      return;
    }
    if (url.pathname === "/api/ai/agents" && method === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const created = {
        ...body,
        id: agentId,
        organization_id: organizationId,
        status: "active",
        config_version: 1,
        is_default: false,
        created_at: now,
        updated_at: now,
      };
      agents = [created];
      await route.fulfill({ status: 201, json: created });
      return;
    }
    if (url.pathname === `/api/ai/agents/${agentId}/audit`) {
      await route.fulfill({ status: 200, json: {
        items: [{
          id: "00000000-0000-0000-0000-000000000007",
          ai_agent_id: agentId,
          actor_user_id: "owner-1",
          actor_name: "Workspace Owner",
          event_type: "created",
          config_version: 1,
          details: { name: "Returns assistant", knowledge_base_ids: ["00000000-0000-0000-0000-000000000006"] },
          created_at: now,
        }],
        total: 1,
        limit: 20,
        offset: 0,
      } });
      return;
    }
    if (url.pathname === "/api/ai/playground" && method === "POST") {
      submittedPlaygroundRequest = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ status: 202, json: { id: executionId, ai_agent_id: "9aa5f49c-c5b4-4e55-b34c-67a9cff31610", ai_agent_config_version: 1, kind: "playground", status: "queued", safe_summary: "Answer queued", draft: null, citations: [], tool_outcomes: [], usage: { prompt_tokens: null, completion_tokens: null, total_tokens: null }, model_name: null, error_code: null, created_at: now, updated_at: now, started_at: null, completed_at: null } });
      return;
    }
    if (url.pathname === `/api/ai/executions/${executionId}`) {
      await route.fulfill({ status: 200, json: { id: executionId, ai_agent_id: "9aa5f49c-c5b4-4e55-b34c-67a9cff31610", ai_agent_config_version: 1, kind: "playground", status: "succeeded", safe_summary: "Answer generated using 1 knowledge source.", draft: "Unused items may be returned within 30 days.", citations: [{ document_id: documentId, document_name: "returns-policy.txt", chunk_index: 0, excerpt: "Unused items may be returned within 30 days with proof of purchase." }], tool_outcomes: [{ tool: "tenant_knowledge_search", status: "completed", result_count: 1 }], usage: { prompt_tokens: 24, completion_tokens: 12, total_tokens: 36 }, model_name: "test-model", error_code: null, created_at: now, updated_at: now, started_at: now, completed_at: now } });
      return;
    }
    if (new URL(route.request().url()).pathname.startsWith("/api/knowledge/gaps")) {
      await route.fulfill({ status: 200, json: new URL(route.request().url()).pathname.endsWith("/durable-groups") ? [] : { items: [], has_more: false } });
      return;
    }
    await route.fulfill({ status: 200, json: {} });
  });

  await page.goto("/dashboard/knowledge");
  await page.getByRole("button", { name: "New", exact: true }).click();
  await page.getByLabel("Knowledge base name", { exact: true }).fill("Returns policies");
  await page.getByRole("button", { name: "Create base" }).click();
  await expect(page.getByRole("tab", { name: "Returns policies", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Edit library details" }).click();
  await page.getByLabel("Knowledge base name", { exact: true }).fill("Returns policy library");
  await page.getByLabel("Knowledge base description").fill("Return and exchange guidance");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Returns policy library", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await page.getByLabel("Choose documents to upload").setInputFiles({
    name: "returns-policy.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Unused items may be returned within 30 days with proof of purchase."),
  });
  await page.getByRole("button", { name: "Upload files" }).click();
  await page.getByRole("button", { name: "Done", exact: true }).click();
  await expect(page.getByRole("link", { name: "returns-policy.txt" })).toBeVisible();
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();

  await page.goto("/dashboard/ai/agents");
  await page.getByRole("button", { name: "New bot" }).click();
  await page.getByLabel("Bot name").fill("Returns assistant");
  await page.getByLabel("System instructions").fill("Answer from the assigned return policy only.");
  await page.getByLabel("Returns policy library").check();
  await page.getByRole("button", { name: "Create bot" }).click();
  await expect(page.getByRole("heading", { name: "Bot configuration" })).toBeVisible();
  await expect(page.getByLabel("Returns policy library")).toBeChecked();
  await expect(page.getByRole("heading", { name: "Configuration history" })).toBeVisible();
  await expect(page.getByText("Bot created")).toBeVisible();

  await page.goto("/dashboard/ai");
  await page.getByLabel("AI bot").selectOption(agentId);
  await page.getByLabel("Question").fill("What is the return window?");
  await page.getByRole("button", { name: "Generate answer" }).click();
  await expect.poll(() => submittedPlaygroundRequest).toBeTruthy();
  await expect(page.getByText("Unused items may be returned within 30 days.")).toBeVisible();
  await expect(page.getByText("returns-policy.txt · section 1")).toBeVisible();
  expect(submittedPlaygroundRequest).toMatchObject({ ai_agent_id: agentId, question: "What is the return window?" });

  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
});

test("viewer can read knowledge and bots but cannot access configuration controls", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      await route.fulfill({ status: 200, json: { id: "viewer-1", email: "viewer@example.com", full_name: "Read Only", role: "viewer", is_active: true, organization: { id: organizationId, name: "Demo Workspace", slug: "demo" } } });
      return;
    }
    if (url.pathname === "/api/health/ready") {
      await route.fulfill({ status: 200, json: { status: "ready", checks: { database: "connected" } } });
      return;
    }
    if (url.pathname === "/api/knowledge/bases") {
      await route.fulfill({ status: 200, json: { items: [defaultBase], total: 1, limit: 100, offset: 0 } });
      return;
    }
    if (url.pathname === "/api/knowledge/documents") {
      await route.fulfill({ status: 200, json: { items: [{ id: "doc-1", organization_id: organizationId, knowledge_base_id: defaultBase.id, name: "returns-policy.txt", content_type: "text/plain", size_bytes: 80, status: "ready", uploaded_by_user_id: "owner-1", deleted_at: null, created_at: now, updated_at: now, jobs: [] }], total: 1, limit: 50, offset: 0 } });
      return;
    }
    if (url.pathname === "/api/ai/agents") {
      await route.fulfill({ status: 200, json: { items: [{ id: "agent-default", name: "SupportPilot Assistant", system_instructions: "", status: "active", config_version: 1, is_default: true, knowledge_base_ids: [defaultBase.id], created_at: now, updated_at: now }], total: 1, limit: 50, offset: 0 } });
      return;
    }
    if (new URL(route.request().url()).pathname.startsWith("/api/knowledge/gaps")) {
      await route.fulfill({ status: 200, json: new URL(route.request().url()).pathname.endsWith("/durable-groups") ? [] : { items: [], has_more: false } });
      return;
    }
    await route.fulfill({ status: 200, json: {} });
  });

  await page.goto("/dashboard/knowledge");
  await expect(page.getByText(/read-only access to knowledge settings/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "New", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Archive General" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reprocess returns-policy.txt" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Delete returns-policy.txt" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "returns-policy.txt" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.goto("/dashboard/ai/agents");
  await expect(page.getByRole("status").filter({ hasText: "read-only access to AI bot settings" })).toBeVisible();
  await expect(page.getByRole("button", { name: "New bot" })).toHaveCount(0);
  await page.getByRole("button", { name: /SupportPilot Assistant/ }).click();
  await expect(page.getByLabel("Bot name")).toBeDisabled();
  await expect(page.getByLabel(defaultBase.name)).toBeDisabled();
  await expect(page.getByRole("button", { name: "Save changes" })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
});

test("agent has read-only knowledge and bot controls on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockRoleWorkspace(page, "agent");

  await page.goto("/dashboard/knowledge");
  await expect(page.getByText(/read-only access to knowledge settings/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "New", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Knowledge base name", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Archive General" })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  let accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);

  await page.goto("/dashboard/ai/agents");
  await expect(page.getByRole("status").filter({ hasText: "read-only access to AI bot settings" })).toBeVisible();
  await expect(page.getByRole("button", { name: "New bot" })).toHaveCount(0);
  await page.getByRole("button", { name: /SupportPilot Assistant/ }).click();
  await expect(page.getByLabel("Bot name")).toBeDisabled();
  await expect(page.getByLabel("System instructions")).toBeDisabled();
  await expect(page.getByLabel("General")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Save changes" })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
});

test("admin can manage knowledge bases and bots on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockRoleWorkspace(page, "admin");

  await page.goto("/dashboard/knowledge");
  await expect(page.getByRole("button", { name: "Upload", exact: true })).toBeVisible();
  await expect(page.getByLabel("Knowledge base name", { exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  let accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);

  await page.goto("/dashboard/ai/agents");
  await expect(page.getByRole("button", { name: "New bot" })).toBeVisible();
  await page.getByRole("button", { name: /SupportPilot Assistant/ }).click();
  await expect(page.getByLabel("Bot name")).toBeEnabled();
  await expect(page.getByLabel("System instructions")).toBeEnabled();
  await expect(page.getByLabel("General")).toBeEnabled();
  await expect(page.getByRole("button", { name: "Save changes" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
});

test("customer questions open from the Knowledge submenu", async ({ page }) => {
  await mockRoleWorkspace(page, "admin");
  await page.goto("/dashboard/knowledge");
  await expect(page.getByRole("heading", { name: "Knowledge bases" })).toBeVisible();
  await expect(page.getByText("Unanswered customer questions", { exact: true })).toHaveCount(0);

  const nav = page.getByRole("navigation", { name: "Main navigation" });
  const questions = nav.getByRole("link", { name: "Customer questions" });
  await questions.click();
  await expect(questions).toHaveAttribute("aria-current", "page");
  await expect(nav.getByRole("link", { name: "Knowledge", exact: true })).not.toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "Customer questions", exact: true })).toBeVisible();
  await expect(page.getByText("No unanswered questions", { exact: true })).toBeVisible();
});

test("customer questions open, save, and publish an answer in a right-side drawer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 840 });
  await mockRoleWorkspace(page, "admin");
  await page.route("**/api/knowledge/gaps/dashboard?**", (route) => route.fulfill({
    json: {
      counts: { total: 2, open: 2, resolved: 0, grouped: 2, groups: 1 },
      items: [{ id: "group-1", representative: "Returns & refunds", questions: [
        { id: "gap-1", question: "How can I return an item?", created_at: now },
        { id: "gap-2", question: "Can I send an item back?", created_at: now },
      ] }],
      has_more: false,
    },
  }));
  await page.route("**/api/knowledge/gaps/groups/publish", (route) => route.fulfill({
    json: { document_id: "faq-1", status: "queued", already_submitted: false },
  }));
  await page.goto("/dashboard/knowledge/customer-questions");
  await expect(page.getByRole("button", { name: "All questions 2" })).toBeVisible();
  const create = page.getByRole("button", { name: "Create answer" });
  await create.click();
  const drawer = page.getByRole("dialog", { name: "Returns & refunds" });
  await expect(drawer.getByText("This answer will cover 2 questions")).toBeVisible();
  await expect.poll(() => drawer.evaluate((element) => Math.round(element.getBoundingClientRect().right))).toBe(390);
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(create).toBeFocused();
  await create.click();
  await drawer.getByRole("textbox", { name: "Verified answer" }).fill("Contact support to request a return.");
  await drawer.getByRole("button", { name: "Save draft" }).click();
  await expect(drawer).toBeHidden();
  await expect(page.getByText("Draft saved for this visit.")).toBeVisible();
  await create.click();
  await expect(drawer.getByRole("textbox", { name: "Verified answer" })).toHaveValue("Contact support to request a return.");
  const submission = page.waitForRequest("**/api/knowledge/gaps/groups/publish");
  await drawer.getByRole("button", { name: "Publish answer" }).click();
  expect((await submission).postDataJSON()).toMatchObject({
    gap_ids: ["gap-1", "gap-2"],
    knowledge_base_id: defaultBase.id,
    answer: "Contact support to request a return.",
  });
  await expect(drawer).toBeHidden();
  await expect(page.getByText(/Answer submitted/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

async function mockRoleWorkspace(page: import("@playwright/test").Page, role: "admin" | "agent" | "viewer") {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      await route.fulfill({ status: 200, json: { id: `${role}-1`, email: `${role}@example.com`, full_name: "Read Only", role, is_active: true, organization: { id: organizationId, name: "Demo Workspace", slug: "demo" } } });
      return;
    }
    if (url.pathname === "/api/health/ready") {
      await route.fulfill({ status: 200, json: { status: "ready", checks: { database: "connected" } } });
      return;
    }
    if (url.pathname === "/api/knowledge/bases") {
      await route.fulfill({ status: 200, json: { items: [defaultBase], total: 1, limit: 100, offset: 0 } });
      return;
    }
    if (url.pathname === `/api/knowledge/bases/${defaultBase.id}/audit`) {
      await route.fulfill({ status: 200, json: { items: [], total: 0, limit: 10, offset: 0 } });
      return;
    }
    if (url.pathname === "/api/knowledge/documents") {
      await route.fulfill({ status: 200, json: { items: [{ id: "doc-1", organization_id: organizationId, knowledge_base_id: defaultBase.id, name: "returns-policy.txt", content_type: "text/plain", size_bytes: 80, status: "ready", uploaded_by_user_id: "owner-1", deleted_at: null, created_at: now, updated_at: now, jobs: [] }], total: 1, limit: 50, offset: 0 } });
      return;
    }
    if (url.pathname === "/api/ai/agents") {
      await route.fulfill({ status: 200, json: { items: [{ id: "agent-default", name: "SupportPilot Assistant", system_instructions: "", status: "active", config_version: 1, is_default: true, knowledge_base_ids: [defaultBase.id], created_at: now, updated_at: now }], total: 1, limit: 50, offset: 0 } });
      return;
    }
    if (url.pathname === "/api/ai/agents/agent-default/audit") {
      await route.fulfill({ status: 200, json: { items: [], total: 0, limit: 20, offset: 0 } });
      return;
    }
    if (new URL(route.request().url()).pathname.startsWith("/api/knowledge/gaps")) {
      await route.fulfill({ status: 200, json: url.pathname.endsWith("/dashboard")
        ? { items: [], counts: { total: 0, open: 0, resolved: 0, grouped: 0, groups: 0 }, has_more: false }
        : [] });
      return;
    }
    await route.fulfill({ status: 200, json: {} });
  });
}
