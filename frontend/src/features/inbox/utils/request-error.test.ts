import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { formatInboxRequestError } from "./request-error";

describe("formatInboxRequestError", () => {
  it("shows the HTTP status, stable error code, and correlation reference", () => {
    expect(
      formatInboxRequestError(
        new ApiError("An unexpected server error occurred", 500, {
          correlationId: "req-123",
        }),
        "Could not load messages.",
      ),
    ).toBe("An unexpected server error occurred (HTTP 500). Reference: req-123");
  });

  it("keeps actionable proxy and network failure messages", () => {
    expect(
      formatInboxRequestError(
        new ApiError("Backend service is unavailable", 502, {
          code: "backend_unavailable",
          correlationId: "req-456",
        }),
        "Could not load messages.",
      ),
    ).toBe("Backend service is unavailable (HTTP 502 · backend_unavailable). Reference: req-456");
    expect(
      formatInboxRequestError(new TypeError("fetch failed"), "Could not load messages."),
    ).toContain("/health/ready");
  });

  it("uses the fallback for errors without a message", () => {
    expect(formatInboxRequestError(null, "Could not load messages.")).toBe(
      "Could not load messages.",
    );
  });
});
