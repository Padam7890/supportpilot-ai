import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShopifyIntegrationCard } from "./shopify-integration-card";

const {
  connectConfiguredShopifyStore,
  disconnectShopify,
  getShopifyStatus,
  getCatalogStatus,
  getCatalogSyncJob,
  startCatalogSync,
  getCurrentUser,
} = vi.hoisted(() => ({
  connectConfiguredShopifyStore: vi.fn(),
  disconnectShopify: vi.fn(),
  getShopifyStatus: vi.fn(),
  getCatalogStatus: vi.fn(),
  getCatalogSyncJob: vi.fn(),
  startCatalogSync: vi.fn(),
  getCurrentUser: vi.fn(),
}));

vi.mock("@/features/integrations/api/shopify-api", () => ({
  connectConfiguredShopifyStore,
  disconnectShopify,
  getShopifyStatus,
  getCatalogStatus,
  getCatalogSyncJob,
  startCatalogSync,
  shopifyQueryKeys: {
    status: ["shopify", "status"],
    catalogStatus: ["shopify", "catalog-status"],
    catalogJob: (jobId: string) => ["shopify", "catalog-sync-job", jobId],
  },
}));

vi.mock("@/features/auth/api/auth-api", () => ({
  getCurrentUser,
  currentUserQueryKey: ["me"],
}));

function renderCard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><ShopifyIntegrationCard/></QueryClientProvider>);
}

describe("Shopify configured-store connection", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    const connected = {
      configured: false,
      connected: true,
      client_credentials_available: true,
      configured_store_domain: "supportpilot-demo-stor.myshopify.com",
      shop_domain: "supportpilot-demo-stor.myshopify.com",
      granted_scopes: ["read_customers", "write_orders", "read_products"],
      reconnect_required: false,
    };
    getShopifyStatus.mockResolvedValue(connected);
    getCatalogStatus.mockResolvedValue({
      connected: true,
      product_scope_granted: true,
      product_count: 0,
      last_sync_at: null,
      last_error_code: null,
    });
    getCurrentUser.mockResolvedValue({ id: "owner-id", role: "owner" });
    getCatalogSyncJob.mockResolvedValue({ id: "sync-id", mode: "full", status: "succeeded", records_seen: 4, attempt_count: 1, max_attempts: 5, last_error_code: null, created_at: "2026-11-01T00:00:00Z", completed_at: "2026-11-01T00:00:01Z" });
    startCatalogSync.mockResolvedValue({ id: "sync-id", mode: "full", status: "queued", records_seen: 0, attempt_count: 0, max_attempts: 5, last_error_code: null, created_at: "2026-11-01T00:00:00Z", completed_at: null });
    connectConfiguredShopifyStore.mockResolvedValue(connected);
  });

  it("connects the configured store through the server API without redirecting through OAuth", async () => {
    getShopifyStatus.mockResolvedValueOnce({
      configured: false,
      connected: false,
      client_credentials_available: true,
      configured_store_domain: "supportpilot-demo-stor.myshopify.com",
      granted_scopes: [],
      reconnect_required: false,
    });
    const view = renderCard();
    fireEvent.click(await view.findByRole("button", { name: "Connect configured store" }));

    await waitFor(() => expect(connectConfiguredShopifyStore).toHaveBeenCalledOnce());
    expect(await view.findByText("Connected · supportpilot-demo-stor.myshopify.com")).toBeInTheDocument();
  });

  it("shows granted scopes and catalog inventory with an owner sync action", async () => {
    const view = renderCard();
    expect(await view.findByText("3 Shopify scopes granted")).toBeInTheDocument();
    expect(await view.findAllByText("read_products")).toHaveLength(2);
    await view.findByText("No successful product sync yet");
    expect(view.container.textContent).toContain("0 synced products");
    expect(await view.findByRole("button", { name: "Sync catalog" })).toBeEnabled();
  });

  it("distinguishes a successful empty catalog from a catalog that has never synced", async () => {
    getCatalogStatus.mockResolvedValueOnce({
      connected: true,
      product_scope_granted: true,
      product_count: 0,
      last_sync_at: "2026-11-01T08:00:00Z",
      last_error_code: null,
    });

    const view = renderCard();

    expect(await view.findByText(/last catalog sync succeeded but Shopify returned no products/i)).toBeInTheDocument();
    expect(view.queryByText("No successful product sync yet")).not.toBeInTheDocument();
  });

  it("starts a full catalog sync for an owner", async () => {
    const view = renderCard();
    await waitFor(() => expect(getCatalogStatus).toHaveBeenCalled());
    await view.findByText("No successful product sync yet");
    expect(view.container.textContent).toContain("0 synced products");
    const syncButton = await view.findByRole("button", { name: "Sync catalog" });
    expect(syncButton).toBeEnabled();
    fireEvent.click(syncButton);
    await waitFor(() => expect(startCatalogSync).toHaveBeenCalledOnce());
    expect(await view.findByText(/Sync status:/)).toBeInTheDocument();
  });

  it("identifies missing product scope and prevents sync until granted", async () => {
    getShopifyStatus.mockResolvedValueOnce({
      configured: false,
      connected: true,
      client_credentials_available: true,
      shop_domain: "supportpilot-demo-stor.myshopify.com",
      granted_scopes: ["read_customers", "write_orders"],
      reconnect_required: false,
    });
    getCatalogStatus.mockResolvedValueOnce({
      connected: true,
      product_scope_granted: false,
      product_count: 0,
      last_sync_at: null,
      last_error_code: null,
    });
    const view = renderCard();
    expect(await view.findByText("2 Shopify scopes granted")).toBeInTheDocument();
    expect(await view.findByText("Product access missing")).toBeInTheDocument();
    expect(await view.findByText("Missing", { selector: "span" })).toBeInTheDocument();
    expect(view.container.textContent).toContain("include read_products, then reconnect");
    expect(view.getByRole("button", { name: "Sync catalog" })).toBeDisabled();
  });
});
