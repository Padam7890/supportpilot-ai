import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { ShopifyOrderLookup } from "./shopify-order-lookup";

const { getShopifyStatus, getShopifyOrders, getVerifiedShopifyOrders, getVerifiedShopifyOrder } = vi.hoisted(() => ({
  getShopifyStatus: vi.fn(),
  getShopifyOrders: vi.fn(),
  getVerifiedShopifyOrders: vi.fn(),
  getVerifiedShopifyOrder: vi.fn(),
}));

vi.mock("@/features/integrations/api/shopify-api", () => ({
  shopifyQueryKeys: {
    status: ["shopify", "status"],
    orders: (email: string, number: string, cursor?: string) => ["shopify", "orders", email, number, cursor],
    orderPages: () => ["shopify", "order-pages"],
  },
  getShopifyStatus,
  getShopifyOrders,
  getVerifiedShopifyOrders,
  getVerifiedShopifyOrder,
}));

const order = {
  id: "gid://shopify/Order/1001",
  order_number: "#1001",
  created_at: "2026-10-30T12:00:00Z",
  financial_status: "PAID",
  fulfillment_status: "FULFILLED",
  total_amount: "42.50",
  currency: "USD",
  tracking: [{ company: "UPS", number: "1Z999", url: "https://track.example/1Z999" }],
};

function renderOrders() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><ShopifyOrderLookup/></QueryClientProvider>);
}

describe("Shopify order verification", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    getShopifyStatus.mockResolvedValue({ configured: true, connected: true, shop_domain: "demo.myshopify.com", granted_scopes: ["read_orders", "read_customers"], reconnect_required: false });
    getShopifyOrders.mockResolvedValue({ items: [order], has_next_page: false, next_cursor: null });
    getVerifiedShopifyOrders.mockResolvedValue({
      customer: { display_name: "Morgan Buyer", email: "morgan@example.test", verified_by: "order_number_and_email" },
      matched_order: order,
      recent_orders: [order],
      has_next_page: false,
      next_cursor: null,
    });
    getVerifiedShopifyOrder.mockResolvedValue(order);
  });

  it("requires both customer email and order number before showing verified details", async () => {
    const view = renderOrders();
    expect(await view.findByRole("heading", { name: "Store orders" })).toBeInTheDocument();
    expect(await view.findByText("#1001")).toBeInTheDocument();
    expect(view.getByText("Fulfilled")).toBeInTheDocument();
    fireEvent.change(await view.findByLabelText("Customer email"), { target: { value: "morgan@example.test" } });
    fireEvent.change(view.getByLabelText("Shopify order number"), { target: { value: "1001" } });
    fireEvent.click(view.getByRole("button", { name: "Verify and find orders" }));

    expect(await view.findByText("Verified customer order history")).toBeInTheDocument();
    expect(view.getByText("Morgan Buyer · verified by order number and email")).toBeInTheDocument();
    expect(getVerifiedShopifyOrders).toHaveBeenCalledWith({ customer_email: "morgan@example.test", order_number: "1001" });
    expect(view.getByText("UPS · 1Z999")).toBeInTheDocument();
  });

  it("shows an empty state when the connected store has no orders", async () => {
    getShopifyOrders.mockResolvedValueOnce({ items: [], has_next_page: false, next_cursor: null });
    const view = renderOrders();
    expect(await view.findByText("No orders found")).toBeInTheDocument();
  });

  it("shows a retry state when the orders API fails", async () => {
    getShopifyOrders.mockRejectedValueOnce(new ApiError("Shopify has not granted order access.", 403, { code: "shopify_scope_or_data_access_required" }));
    const view = renderOrders();
    expect(await view.findByRole("alert")).toHaveTextContent("Could not load Shopify orders. Shopify has not granted order access.");
    expect(view.getByRole("alert")).toHaveTextContent("API status 403 · shopify_scope_or_data_access_required");
  });

  it("explains that the configured development store does not need an HTTPS callback", async () => {
    getShopifyStatus.mockResolvedValueOnce({
      configured: false,
      connected: false,
      client_credentials_available: true,
      configured_store_domain: "supportpilot-demo-stor.myshopify.com",
    });
    const view = renderOrders();

    expect(await view.findByRole("heading", { name: "Connect the configured Shopify store" })).toBeInTheDocument();
    expect(view.getByText(/does not need an HTTPS callback/i)).toBeInTheDocument();
    expect(view.getByRole("link", { name: "Open integrations" })).toHaveAttribute("href", "/dashboard/settings#integrations");
  });

  it("does not display order history when Shopify rejects the identity match", async () => {
    getVerifiedShopifyOrders.mockRejectedValue(new Error("No order matched both the order number and customer email"));
    const view = renderOrders();
    fireEvent.change(await view.findByLabelText("Customer email"), { target: { value: "morgan@example.test" } });
    fireEvent.change(view.getByLabelText("Shopify order number"), { target: { value: "9999" } });
    fireEvent.click(view.getByRole("button", { name: "Verify and find orders" }));
    await waitFor(() => expect(view.getByRole("alert")).toBeInTheDocument());
    expect(view.queryByText("Verified customer order history")).not.toBeInTheDocument();
  });
});
