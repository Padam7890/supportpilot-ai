import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommandSearch } from "./command-search";

const { searchWorkspace } = vi.hoisted(() => ({ searchWorkspace: vi.fn() }));
vi.mock("../api/search-api", () => ({ searchWorkspace }));
vi.mock("@/features/auth/api/auth-api", () => ({
  currentUserQueryKey: ["me"],
  getCurrentUser: vi.fn().mockResolvedValue({ id: "user-1", organization_id: "org-1", email: "agent@example.com", full_name: "Agent", role: "owner", is_active: true, organization: { id: "org-1", name: "Support", slug: "support" } }),
}));
vi.mock("next/link", () => ({ default: ({ href, children, onClick, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props} onClick={(event) => { event.preventDefault(); onClick?.(event); }}>{children}</a> }));

describe("command search", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    searchWorkspace.mockResolvedValue({
      query: "delivery",
      limit_per_kind: 5,
      items: [{ kind: "ticket", id: "ticket-id", title: "Order delivery question", subtitle: "Morgan Example · open ticket", href: "/dashboard/tickets/ticket-id" }],
    });
  });

  it("opens from the keyboard shortcut and shows tenant search results", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CommandSearch/></QueryClientProvider>);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = screen.getByLabelText("Search pages, tickets, customers, and documents");
    fireEvent.change(input, { target: { value: "delivery" } });
    const result = await screen.findByRole("option", { name: /Order delivery question/ });
    expect(result).toHaveAttribute("aria-selected", "true");
    expect(searchWorkspace).toHaveBeenCalledWith("delivery");
    fireEvent.click(result);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
