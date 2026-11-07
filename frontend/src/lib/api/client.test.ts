import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

describe("api error handling", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("preserves problem details and the correlation id for support diagnostics", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            type: "urn:supportpilot:problem:internal_error",
            title: "Internal Server Error",
            status: 500,
            detail: "An unexpected server error occurred",
            code: "internal_error",
            instance: "/api/v1/conversations/123/messages",
          }),
          { status: 500, headers: { "x-correlation-id": "req-123" } },
        ),
      ),
    );

    const request = api("/conversations/123/messages");

    await expect(request).rejects.toMatchObject({
      message: "An unexpected server error occurred",
      status: 500,
      code: "internal_error",
      correlationId: "req-123",
    });
  });

  it("reports HTTP status when the proxy returns a non-JSON error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("Bad Gateway", { status: 502, headers: { "content-type": "text/plain" } }),
      ),
    );

    await expect(api("/conversations/123/messages")).rejects.toMatchObject({
      message: "Request failed (HTTP 502).",
      status: 502,
    });
  });
});
