import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("merges Tailwind utility conflicts while retaining independent classes", () => {
    expect(cn("px-2 text-sm", "px-4 font-semibold")).toBe("text-sm px-4 font-semibold");
  });
});
