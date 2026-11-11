import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const organization = {
  id: "org-1",
  name: "SupportPilot Workspace",
  slug: "supportpilot-workspace",
};

async function mockSettingsApi(
  page: import("@playwright/test").Page,
  role: "owner" | "viewer",
) {
  let currentOrganization = { ...organization };
  const requests: string[] = [];

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    requests.push(`${method} ${url.pathname}`);

    if (url.pathname === "/api/auth/me") {
      await route.fulfill({
        status: 200,
        json: {
          id: "user-1",
          email: `${role}@example.test`,
          full_name: role === "owner" ? "Workspace Owner" : "Read Only",
          role,
          is_active: true,
          organization: currentOrganization,
        },
      });
      return;
    }
    if (url.pathname === "/api/health/ready") {
      await route.fulfill({ status: 200, json: { status: "ready", checks: {} } });
      return;
    }
    if (url.pathname === "/api/organization" && method === "GET") {
      await route.fulfill({ status: 200, json: currentOrganization });
      return;
    }
    if (url.pathname === "/api/organization" && method === "PATCH") {
      currentOrganization = { ...currentOrganization, ...route.request().postDataJSON() };
      await route.fulfill({ status: 200, json: currentOrganization });
      return;
    }
    if (url.pathname === "/api/users" || url.pathname === "/api/users/invitations") {
      await route.fulfill({ status: 200, json: [] });
      return;
    }
    if (url.pathname === "/api/auth/sessions") {
      await route.fulfill({ status: 200, json: { items: [], total: 0, limit: 25, offset: 0 } });
      return;
    }

    await route.fulfill({ status: 200, json: route.request().url().includes("/api/teams") ? [] : {} });
  });

  return requests;
}

test("workspace owner settings deep links round-trip organization changes", async ({ page }) => {
  const requests = await mockSettingsApi(page, "owner");
  await page.goto("/dashboard/settings#team");

  await expect(page.getByRole("heading", { name: "Team & roles" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Team & roles" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Security" })).toHaveCount(0);

  await page.getByRole("button", { name: "General" }).click();
  await expect(page).toHaveURL(/\/dashboard\/settings#general$/);
  await page.getByLabel("Workspace name").fill("Updated Support Workspace");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Workspace updated." })).toBeVisible();
  expect(requests).toContain("PATCH /api/organization");

  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? ""))).toEqual([]);
});

test("viewer opening a restricted settings link is kept in account security", async ({ page }) => {
  const requests = await mockSettingsApi(page, "viewer");
  await page.goto("/dashboard/settings#team");

  await expect(page.getByRole("heading", { name: "Security and sessions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Team & roles" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Security" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("No active refresh sessions were found.")).toBeVisible();
  expect(requests).not.toContain("GET /api/users");
  expect(requests).not.toContain("GET /api/organization");
});
