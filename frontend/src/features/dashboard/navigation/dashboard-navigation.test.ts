import { describe, expect, it } from "vitest";
import {
  getDashboardNavigation,
  isDashboardNavigationLinkActive,
} from "@/features/dashboard/navigation/dashboard-navigation";

describe("dashboard navigation", () => {
  it("groups implemented routes and keeps workspace security inside settings", () => {
    const groups = getDashboardNavigation("owner");
    expect(groups.map((group) => group.label)).toEqual([
      "Main",
      "AI & automation",
      "Insights",
      "Workspace",
    ]);
    expect(groups.flatMap((group) => group.links).map((link) => link.href)).not.toContain(
      "/dashboard/security",
    );
  });

  it("hides operational activity from viewer navigation", () => {
    const viewerRoutes = getDashboardNavigation("viewer").flatMap((group) => group.links);
    expect(viewerRoutes.some((link) => link.href === "/dashboard/operations")).toBe(false);
  });

  it("nests customer questions under Knowledge for workspace managers", () => {
    const route = "/dashboard/knowledge/customer-questions";
    for (const role of ["owner", "admin"]) {
      const links = getDashboardNavigation(role).flatMap((group) => group.links);
      expect(links.find((link) => link.href === route)).toMatchObject({
        label: "Customer questions",
        parentHref: "/dashboard/knowledge",
      });
    }
    for (const role of ["agent", "viewer"]) {
      const links = getDashboardNavigation(role).flatMap((group) => group.links);
      expect(links.some((link) => link.href === route)).toBe(false);
    }
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

  it("marks an integration subsection active on the settings route", () => {
    const integration = getDashboardNavigation("owner").flatMap((group) => group.links).find((link) => link.label === "Integrations");
    expect(integration).toBeDefined();
    if (!integration) throw new Error("Expected an integration navigation entry");
    expect(isDashboardNavigationLinkActive("/dashboard/settings", integration)).toBe(true);
  });
});
