import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SecuritySessions } from "./security-sessions";

const { listAuthSessions, revokeAuthSession } = vi.hoisted(() => ({
  listAuthSessions: vi.fn(),
  revokeAuthSession: vi.fn(),
}));

vi.mock("../api/auth-api", () => ({ listAuthSessions, revokeAuthSession }));

describe("security sessions", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    listAuthSessions.mockResolvedValue({
      items: [{ id: "session-one", created_at: "2026-10-31T10:00:00Z", expires_at: "2026-11-07T10:00:00Z" }],
      total: 1,
      limit: 50,
      offset: 0,
    });
    revokeAuthSession.mockResolvedValue(undefined);
  });

  it("shows the token expiry boundary and lets the user revoke a refresh session", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><SecuritySessions/></QueryClientProvider>);

    expect(await screen.findByText("Sign-in session")).toBeInTheDocument();
    expect(screen.getByText(/access token already issued.*short expiry/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(revokeAuthSession.mock.calls[0]?.[0]).toBe("session-one"));
    expect(await screen.findByText("Session refresh access revoked.")).toBeInTheDocument();
  });

  it("paginates beyond the first bounded page and reports the visible range", async () => {
    listAuthSessions.mockImplementation(async (offset = 0) => ({
      items: [{ id: `session-${offset + 1}`, created_at: "2026-10-31T10:00:00Z", expires_at: "2026-11-07T10:00:00Z" }],
      total: 26,
      limit: 25,
      offset,
    }));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><SecuritySessions/></QueryClientProvider>);

    expect(await screen.findByText("Showing 1–1 of 26 active sessions")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText("Showing 26–26 of 26 active sessions")).toBeInTheDocument();
    expect(listAuthSessions).toHaveBeenLastCalledWith(25);
  });
});
