import { describe, expect, it } from "vitest";
import {
  getDashboardNavigation,
  isDashboardNavigationLinkActive,
} from "@/features/dashboard/navigation/dashboard-navigation";

describe("dashboard navigation", () => {
  it("groups implemented workspace routes without exposing security as a separate menu", () => {
    const groups = getDashboardNavigation("owner");
    expect(groups.map((group) => group.label)).toEqual([
      "Workspace",
      "AI Studio",
      "Connections",
      "Administration",
    ]);
    expect(groups.flatMap((group) => group.links).map((link) => link.href)).not.toContain(
      "/dashboard/security",
    );
  });

  it("uses role-aware settings labels", () => {
    const managerSettings = getDashboardNavigation("admin")
      .flatMap((group) => group.links)
      .find((link) => link.href === "/dashboard/settings");
    const viewerSettings = getDashboardNavigation("viewer")
      .flatMap((group) => group.links)
      .find((link) => link.href === "/dashboard/settings");

    expect(managerSettings?.label).toBe("Settings & team");
    expect(viewerSettings?.label).toBe("Settings");
  });

  it("matches nested routes and avoids treating overview as active on every page", () => {
    const groups = getDashboardNavigation("agent");
    const links = groups.flatMap((group) => group.links);
    const inbox = links.find((link) => link.href === "/dashboard/inbox");
    const overview = links.find((link) => link.href === "/dashboard");

    expect(inbox).toBeDefined();
    expect(overview).toBeDefined();
    if (!inbox || !overview) throw new Error("Expected primary dashboard links");
    expect(isDashboardNavigationLinkActive("/dashboard/inbox/ticket-1", inbox)).toBe(true);
    expect(isDashboardNavigationLinkActive("/dashboard/inbox", overview)).toBe(false);
    expect(isDashboardNavigationLinkActive("/dashboard", overview)).toBe(true);
  });
});
