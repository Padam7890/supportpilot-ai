import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type IntegrationConnection = components["schemas"]["IntegrationConnectionOut"];
export type IntegrationConnectionList = components["schemas"]["IntegrationConnectionListOut"];
export type IntegrationConnectionAuditPage = components["schemas"]["IntegrationConnectionAuditPageOut"];
export type IntegrationWebhookEventPage = components["schemas"]["IntegrationWebhookEventPageOut"];
export type IntegrationWebhookRetry = components["schemas"]["IntegrationWebhookRetryOut"];
export type IntegrationDeliveryPage = components["schemas"]["IntegrationDeliveryPageOut"];
export type IntegrationDeliveryRetry = components["schemas"]["IntegrationDeliveryRetryOut"];
export type IntegrationProvider = components["schemas"]["IntegrationProviderOut"];
export type ShopifyAccessAuditPage = components["schemas"]["ShopifyAccessAuditPageOut"];

export const integrationManagementQueryKeys = {
  connections: ["integration-connections"] as const,
  connectionAudit: (connectionId: string | undefined) => ["integration-connection-audit", connectionId] as const,
  providers: ["integration-providers"] as const,
  events: (connectionId: string | undefined) => ["integration-events", connectionId] as const,
  deliveries: (connectionId: string | undefined) => ["integration-deliveries", connectionId] as const,
  accessAudit: (connectionId: string | undefined) => ["shopify-access-audit", connectionId] as const,
};

export const getIntegrationConnections = () =>
  api<IntegrationConnectionList>("/integrations/connections?limit=100&offset=0");

export const updateConnectionBotRouting = (connectionId: string, aiAgentId: string | null) =>
  api<IntegrationConnection>(`/integrations/connections/${encodeURIComponent(connectionId)}/routing`, {
    method: "PATCH",
    body: JSON.stringify({ ai_agent_id: aiAgentId }),
  });

export const getIntegrationConnectionAudit = (connectionId: string) =>
  api<IntegrationConnectionAuditPage>(
    `/integrations/connections/${encodeURIComponent(connectionId)}/audit?limit=10&offset=0`,
  );

export const getIntegrationProviders = () =>
  api<IntegrationProvider[]>("/integrations/providers");

export const getConnectionEvents = (connectionId: string) =>
  api<IntegrationWebhookEventPage>(
    `/integrations/connections/${encodeURIComponent(connectionId)}/events?limit=10&offset=0`,
  );

export const retryConnectionEvent = (connectionId: string, eventId: string) =>
  api<IntegrationWebhookRetry>(
    `/integrations/connections/${encodeURIComponent(connectionId)}/events/${encodeURIComponent(eventId)}/retry`,
    { method: "POST" },
  );

export const getConnectionDeliveries = (connectionId: string) =>
  api<IntegrationDeliveryPage>(
    `/integrations/connections/${encodeURIComponent(connectionId)}/deliveries?limit=10&offset=0`,
  );

export const retryConnectionDelivery = (connectionId: string, deliveryId: string) =>
  api<IntegrationDeliveryRetry>(
    `/integrations/connections/${encodeURIComponent(connectionId)}/deliveries/${encodeURIComponent(deliveryId)}/retry`,
    { method: "POST" },
  );

export const getShopifyAccessAudit = (connectionId: string) =>
  api<ShopifyAccessAuditPage>(
    `/integrations/connections/${encodeURIComponent(connectionId)}/access-audit?limit=10&offset=0`,
  );
