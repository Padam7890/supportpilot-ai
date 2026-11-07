import { describe, expect, it } from "vitest";
import { settingsSectionFromHash, settingsSectionHash } from "./settings-section";

describe("settings section navigation", () => {
  it.each(["general", "team", "security", "recommendations", "widget", "shopify"] as const)(
    "round-trips the %s section",
    (section) => {
      expect(settingsSectionFromHash(settingsSectionHash(section))).toBe(section);
    },
  );

  it("ignores unknown or malformed hashes", () => {
    expect(settingsSectionFromHash("")).toBeNull();
    expect(settingsSectionFromHash("#billing")).toBeNull();
    expect(settingsSectionFromHash("#widget?x=1")).toBeNull();
  });
});
