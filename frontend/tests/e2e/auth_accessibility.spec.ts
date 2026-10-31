import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("login, registration, and approval-pending screens meet WCAG A/AA checks", async ({ page }) => {
  const screens = [
    { path: "/login", heading: "Sign in to your workspace" },
    { path: "/register", heading: "Request a workspace" },
    { path: "/register/pending", heading: "Your workspace is awaiting review" },
  ];

  for (const screen of screens) {
    await page.goto(screen.path);
    await expect(page.getByRole("heading", { name: screen.heading })).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(
      results.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? "")),
      `${screen.path} has critical or serious accessibility violations`,
    ).toEqual([]);
  }
});
