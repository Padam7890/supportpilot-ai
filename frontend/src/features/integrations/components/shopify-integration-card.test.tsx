import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShopifyIntegrationCard } from "./shopify-integration-card";

const { connectConfiguredShopifyStore, disconnectShopify, getShopifyStatus } = vi.hoisted(() => ({
  connectConfiguredShopifyStore: vi.fn(),
  disconnectShopify: vi.fn(),
  getShopifyStatus: vi.fn(),
}));

vi.mock("@/features/integrations/api/shopify-api", () => ({
  connectConfiguredShopifyStore,
  disconnectShopify,
  getShopifyStatus,
  shopifyQueryKeys: { status: ["shopify", "status"] },
}));

function renderCard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><ShopifyIntegrationCard/></QueryClientProvider>);
}

describe("Shopify configured-store connection", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    getShopifyStatus.mockResolvedValueOnce({
      configured: false,
      connected: false,
      client_credentials_available: true,
      configured_store_domain: "supportpilot-demo-stor.myshopify.com",
    });
    const connected = {
      configured: false,
      connected: true,
      client_credentials_available: true,
      configured_store_domain: "supportpilot-demo-stor.myshopify.com",
      shop_domain: "supportpilot-demo-stor.myshopify.com",
      granted_scopes: ["read_customers", "read_orders"],
      reconnect_required: false,
    };
    connectConfiguredShopifyStore.mockResolvedValue(connected);
    getShopifyStatus.mockResolvedValue(connected);
  });

  it("connects the configured store through the server API without redirecting through OAuth", async () => {
    const view = renderCard();
    fireEvent.click(await view.findByRole("button", { name: "Connect configured store" }));

    await waitFor(() => expect(connectConfiguredShopifyStore).toHaveBeenCalledOnce());
    expect(await view.findByText("Connected · supportpilot-demo-stor.myshopify.com")).toBeInTheDocument();
  });
});
