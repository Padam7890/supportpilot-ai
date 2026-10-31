import axe from "axe-core";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RegistrationPendingPage from "@/app/(auth)/register/pending/page";
import { AuthPanel } from "./auth-form";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

afterEach(() => cleanup());

async function expectNoSeriousA11yViolations() {
  // The component tests render inside jsdom, not the real Next.js document shell.
  document.documentElement.lang = "en";
  document.title = "SupportPilot AI";
  const results = await axe.run(document, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
    // jsdom has no canvas implementation for axe's color-contrast calculation;
    // full-page Playwright axe scans continue to cover contrast in a real browser.
    rules: { "color-contrast": { enabled: false } },
  });
  expect(
    results.violations.filter((violation) => ["critical", "serious"].includes(violation.impact ?? "")),
  ).toEqual([]);
}

describe("authentication accessibility", () => {
  it("checks the login form", async () => {
    render(<AuthPanel mode="login"/>);
    await expectNoSeriousA11yViolations();
  });

  it("checks the registration form", async () => {
    render(<AuthPanel mode="register"/>);
    await expectNoSeriousA11yViolations();
  });

  it("checks the approval-pending page", async () => {
    render(<RegistrationPendingPage/>);
    await expectNoSeriousA11yViolations();
  });
});
