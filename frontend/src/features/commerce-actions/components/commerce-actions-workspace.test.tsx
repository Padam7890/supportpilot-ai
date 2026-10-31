import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommerceActionsWorkspace } from "./commerce-actions-workspace";

const {
  approveCommerceAction,
  cancelCommerceAction,
  createCommerceAction,
  getCommerceActionAudit,
  getCurrentUser,
  listCommerceActions,
  listTickets,
  rejectCommerceAction,
} = vi.hoisted(() => ({
  approveCommerceAction: vi.fn(),
  cancelCommerceAction: vi.fn(),
  createCommerceAction: vi.fn(),
  getCommerceActionAudit: vi.fn(),
  getCurrentUser: vi.fn(),
  listCommerceActions: vi.fn(),
  listTickets: vi.fn(),
  rejectCommerceAction: vi.fn(),
}));

vi.mock("../api/commerce-actions-api", () => ({
  approveCommerceAction,
  cancelCommerceAction,
  commerceActionKeys: {
    list: (status: string | undefined, offset: number) => ["commerce-actions", status, offset],
    audit: (id: string) => ["commerce-action-audit", id],
  },
  createCommerceAction,
  getCommerceActionAudit,
  listCommerceActions,
  rejectCommerceAction,
}));
vi.mock("@/features/auth/api/auth-api", () => ({
  currentUserQueryKey: ["current-user"],
  getCurrentUser,
}));
vi.mock("@/features/tickets/api/ticket-api", () => ({ listTickets }));

const ticket = {
  id: "ticket-one",
  organization_id: "organization-one",
  customer_id: "customer-one",
  assignee_id: null,
  subject: "Damaged order",
  description: null,
  status: "open" as const,
  priority: "normal" as const,
  customer_name: "Morgan Buyer",
  assignee_name: null,
  created_at: "2026-10-31T10:00:00Z",
  updated_at: "2026-10-31T10:00:00Z",
};

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><CommerceActionsWorkspace/></QueryClientProvider>);
}

describe("commerce actions workspace", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "stable-idempotency-key-1234" });
    getCurrentUser.mockResolvedValue({ id: "agent-one", role: "agent" });
    listTickets.mockResolvedValue({ items: [ticket], total: 1, limit: 100, offset: 0 });
    listCommerceActions.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    createCommerceAction.mockResolvedValue({ id: "action-one" });
    getCommerceActionAudit.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
  });

  it("lets an agent submit a ticket-linked refund request with an idempotency key", async () => {
    renderWorkspace();
    const ticketSelect = await screen.findByLabelText("Support ticket");
    await screen.findByRole("option", { name: /Damaged order/ });
    fireEvent.change(ticketSelect, { target: { value: ticket.id } });
    await waitFor(() => expect(ticketSelect).toHaveValue(ticket.id));
    fireEvent.change(screen.getByLabelText("Shopify order number"), { target: { value: "#1001" } });
    fireEvent.change(screen.getByLabelText("Refund amount"), { target: { value: "24.50" } });
    fireEvent.change(screen.getByLabelText("Reason for review"), { target: { value: "Item arrived damaged" } });
    fireEvent.submit(screen.getByRole("button", { name: "Submit for approval" }).closest("form")!);

    await waitFor(() => expect(createCommerceAction).toHaveBeenCalledWith(
      {
        ticket_id: ticket.id,
        order_number: "#1001",
        action_type: "refund",
        refund_amount: 24.5,
        reason: "Item arrived damaged",
      },
      "stable-idempotency-key-1234",
    ));
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByText(/never sends refund or cancellation writes to Shopify/i)).toBeInTheDocument();
  });

  it("keeps viewers read-only", async () => {
    getCurrentUser.mockResolvedValue({ id: "viewer-one", role: "viewer" });
    renderWorkspace();

    expect(await screen.findByRole("heading", { name: "Refund and cancellation requests" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit for approval" })).not.toBeInTheDocument();
    expect(listTickets).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });
});
