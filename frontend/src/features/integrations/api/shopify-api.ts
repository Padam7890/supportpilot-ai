import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type ShopifyStatus = components["schemas"]["ShopifyStatusOut"];
export type ShopifyOrderLookup = components["schemas"]["ShopifyOrderLookupOut"];
export type ShopifyOrder = components["schemas"]["ShopifyOrderOut"];
export type ShopifyOrderPage = components["schemas"]["ShopifyOrderPageOut"];
export type ShopifyOrderSummary = components["schemas"]["ShopifyOrderSummaryOut"];
export type CatalogStatus = components["schemas"]["CatalogStatusOut"];
export type CatalogSyncJob = components["schemas"]["CatalogSyncJobOut"];

export const shopifyQueryKeys = {
  status: ["shopify", "status"] as const,
  catalogStatus: ["shopify", "catalog-status"] as const,
  catalogJob: (jobId: string) => ["shopify", "catalog-sync-job", jobId] as const,
  orders: (email: string, number: string, cursor?: string) => ["shopify", "orders", email, number, cursor] as const,
  orderPages: () => ["shopify", "order-pages"] as const,
};

export const getShopifyStatus = () => api<ShopifyStatus>("/integrations/shopify/status");
export const getCatalogStatus = () => api<CatalogStatus>("/catalog/status");
export const startCatalogSync = () => api<CatalogSyncJob>("/catalog/sync", {
  method: "POST",
  body: JSON.stringify({ mode: "full" }),
});
export const getCatalogSyncJob = (jobId: string) => api<CatalogSyncJob>(`/catalog/sync-jobs/${encodeURIComponent(jobId)}`);

export function getShopifyOrders(values: { limit?: number; cursor?: string } = {}) {
  const query = new URLSearchParams({ limit: String(values.limit ?? 25) });
  if (values.cursor) query.set("cursor", values.cursor);
  return api<ShopifyOrderPage>(`/integrations/shopify/orders/list?${query.toString()}`);
}

export function getVerifiedShopifyOrders(values: { customer_email: string; order_number: string; cursor?: string }) {
  const query = new URLSearchParams({ customer_email: values.customer_email, order_number: values.order_number });
  if (values.cursor) query.set("cursor", values.cursor);
  return api<ShopifyOrderLookup>(`/integrations/shopify/orders?${query.toString()}`);
}

export function getVerifiedShopifyOrder(orderNumber: string, customerEmail: string) {
  const query = new URLSearchParams({ customer_email: customerEmail });
  return api<ShopifyOrder>(`/integrations/shopify/orders/${encodeURIComponent(orderNumber)}?${query.toString()}`);
}

export const disconnectShopify = () =>
  api<{ status: string; message: string; shop_domain?: string | null }>("/integrations/shopify/disconnect", { method: "POST" });

export const connectConfiguredShopifyStore = () =>
  api<ShopifyStatus>("/integrations/shopify/connect-configured-store", { method: "POST" });
