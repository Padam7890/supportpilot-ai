import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommandSearch } from "./command-search";

const { searchWorkspace } = vi.hoisted(() => ({ searchWorkspace: vi.fn() }));
vi.mock("../api/search-api", () => ({ searchWorkspace }));
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
    const input = screen.getByLabelText("Search tickets, customers, or documents");
    fireEvent.change(input, { target: { value: "delivery" } });
    expect(await screen.findByRole("link", { name: /Order delivery question/ })).toHaveAttribute("href", "/dashboard/tickets/ticket-id");
    expect(searchWorkspace).toHaveBeenCalledWith("delivery");
    fireEvent.click(screen.getByRole("link", { name: /Order delivery question/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
