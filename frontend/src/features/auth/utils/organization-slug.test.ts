import { describe, expect, it } from "vitest";
import { organizationSlugFromName } from "./organization-slug";

describe("organizationSlugFromName", () => {
  it.each([
    ["SupportPilot Demo", "supportpilot-demo"],
    ["  Café & Co.  ", "cafe-co"],
    ["IT", "it-workspace"],
    ["नेपाली", ""],
  ])("turns %j into %j", (name, expected) => {
    expect(organizationSlugFromName(name)).toBe(expected);
  });

  it("keeps generated slugs within the API limit", () => {
    expect(organizationSlugFromName("a ".repeat(100)).length).toBeLessThanOrEqual(80);
  });
});
