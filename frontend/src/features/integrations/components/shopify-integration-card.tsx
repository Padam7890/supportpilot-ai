"use client";

import { SupportTraceLink } from "@/components/support-trace-link";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ExternalLink, PackageSearch, RefreshCw, ShieldCheck, Store, Unplug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getCurrentUser, currentUserQueryKey } from "@/features/auth/api/auth-api";
import { ApiError } from "@/lib/api/errors";
import {
  getConnectionDeliveries,
  getConnectionEvents,
  getIntegrationConnectionAudit,
  getIntegrationConnections,
  getIntegrationProviders,
  getShopifyAccessAudit,
  integrationManagementQueryKeys,
  retryConnectionDelivery,
  retryConnectionEvent,
} from "../api/integration-management-api";
import {
  connectConfiguredShopifyStore,
  type CatalogSyncMode,
  disconnectShopify,
  getCatalogStatus,
  getCatalogSyncJobs,
  getCatalogSyncJob,
  getShopifyStatus,
  shopifyQueryKeys,
  startCatalogSync,
} from "../api/shopify-api";

const REQUIRED_SCOPES = [
  { scope: "read_orders", purpose: "Order lookup and tracking" },
  { scope: "read_customers", purpose: "Customer details for verified order lookup" },
  { scope: "read_products", purpose: "Product sync and AI recommendations" },
] as const;

function catalogSyncGuidance(errorCode: string): string {
  switch (errorCode) {
    case "product_scope_missing":
    case "shopify_product_scope_missing":
    case "shopify_required_scopes_missing":
    case "shopify_scope_or_data_access_required":
      return "The active Shopify connection did not provide product data access for this sync. Check the current connection and Shopify’s product access before reconnecting.";
    case "catalog_not_connected":
      return "The catalog job no longer has an active Shopify store connection. Reconnect the intended store, then start a full sync.";
    case "shopify_reauthorization_required":
      return "Shopify credentials need renewal. Use the reconnect action above, then start a full sync.";
    case "shopify_access_denied":
      return "Shopify rejected the product request. Review the latest sync diagnostics and verify the connected store’s product access.";
    case "shopify_rate_limited":
      return "Shopify rate-limited the request. The worker retries transient limits; if the job is terminal, start another sync shortly.";
    case "shopify_graphql_error":
      return "Shopify returned a GraphQL error. Use the support reference below to inspect sanitized provider diagnostics.";
    case "shopify_unavailable":
    case "provider_unavailable":
      return "Shopify could not be reached temporarily. Retry the sync when the store is available.";
    case "catalog_persistence_failed":
      return "Products were fetched but could not be saved. Existing catalog data was retained; check backend database health before retrying.";
    case "worker_lease_expired":
      return "The catalog worker stopped before completing this job. Check worker health, then start another sync.";
    case "shopify_credentials_unavailable":
      return "No usable Shopify credentials were available for this connection. Reconnect the intended store.";
    case "shopify_api_version_invalid":
      return "The configured Shopify API version is invalid. Correct the backend integration configuration before syncing again.";
    case "shopify_invalid_product_response":
    case "shopify_invalid_response":
      return "Shopify returned data SupportPilot could not safely normalize. Review the sanitized provider diagnostics.";
    default:
      return "The latest catalog sync failed. Review its job details and support reference before retrying.";
  }
}

export function ShopifyIntegrationCard() {
  const queryClient = useQueryClient();
  const [shop, setShop] = useState("");
  const [syncJobId, setSyncJobId] = useState<string>();
  const [syncMode, setSyncMode] = useState<CatalogSyncMode>("full");
  const [validationMessage, setValidationMessage] = useState<string>();
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const status = useQuery({ queryKey: shopifyQueryKeys.status, queryFn: getShopifyStatus });
  const catalog = useQuery({
    queryKey: shopifyQueryKeys.catalogStatus,
    queryFn: getCatalogStatus,
    enabled: Boolean(status.data?.connected),
  });
  const me = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const connections = useQuery({
    queryKey: integrationManagementQueryKeys.connections,
    queryFn: getIntegrationConnections,
  });
  const providers = useQuery({
    queryKey: integrationManagementQueryKeys.providers,
    queryFn: getIntegrationProviders,
    enabled: Boolean(status.data?.connected),
  });
  const shopifyCapabilities = providers.data?.find((provider) => provider.provider_id === "shopify")?.capabilities ?? [];
  const shopifyConnection = connections.data?.items.find(
    (connection) =>
      connection.provider_id === "shopify" &&
      connection.external_account_id === status.data?.shop_domain,
  );
  const catalogJobs = useQuery({
    queryKey: [...shopifyQueryKeys.catalogJobs, shopifyConnection?.id],
    queryFn: () => getCatalogSyncJobs(5, shopifyConnection?.id),
    enabled: Boolean(shopifyConnection?.id),
  });
  const connectionEvents = useQuery({
    queryKey: integrationManagementQueryKeys.events(shopifyConnection?.id),
    queryFn: () => {
      if (!shopifyConnection) throw new Error("Shopify connection is not available");
      return getConnectionEvents(shopifyConnection.id);
    },
    enabled: Boolean(shopifyConnection?.id),
  });
  const connectionDeliveries = useQuery({
    queryKey: integrationManagementQueryKeys.deliveries(shopifyConnection?.id),
    queryFn: () => {
      if (!shopifyConnection) throw new Error("Shopify connection is not available");
      return getConnectionDeliveries(shopifyConnection.id);
    },
    enabled: Boolean(shopifyConnection?.id),
  });
  const connectionAudit = useQuery({
    queryKey: integrationManagementQueryKeys.connectionAudit(shopifyConnection?.id),
    queryFn: () => {
      if (!shopifyConnection) throw new Error("Shopify connection is not available");
      return getIntegrationConnectionAudit(shopifyConnection.id);
    },
    enabled: Boolean(shopifyConnection?.id && (me.data?.role === "owner" || me.data?.role === "admin")),
  });
  const accessAudit = useQuery({
    queryKey: integrationManagementQueryKeys.accessAudit(shopifyConnection?.id),
    queryFn: () => {
      if (!shopifyConnection) throw new Error("Shopify connection is not available");
      return getShopifyAccessAudit(shopifyConnection.id);
    },
    enabled: Boolean(shopifyConnection?.id && (me.data?.role === "owner" || me.data?.role === "admin")),
  });
  const syncJob = useQuery({
    queryKey: shopifyQueryKeys.catalogJob(syncJobId ?? ""),
    queryFn: () => getCatalogSyncJob(syncJobId ?? ""),
    enabled: Boolean(syncJobId),
    refetchInterval: (query) => {
      const state = query.state.data?.status;
      return state === "succeeded" || state === "failed" || state === "cancelled" ? false : 2_000;
    },
    refetchIntervalInBackground: false,
  });
  async function invalidateShopifyConnectionState() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.status }),
      queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogStatus }),
      queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogJobs }),
      queryClient.invalidateQueries({ queryKey: integrationManagementQueryKeys.connections }),
      queryClient.invalidateQueries({ queryKey: ["integration-events"] }),
      queryClient.invalidateQueries({ queryKey: ["integration-deliveries"] }),
      queryClient.invalidateQueries({ queryKey: ["shopify-access-audit"] }),
      queryClient.invalidateQueries({ queryKey: ["integration-connection-audit"] }),
    ]);
  }
  const disconnect = useMutation({
    mutationFn: disconnectShopify,
    onSuccess: async () => {
      setConfirmDisconnect(false);
      setSyncJobId(undefined);
      await invalidateShopifyConnectionState();
    },
  });
  const connectConfigured = useMutation({
    mutationFn: connectConfiguredShopifyStore,
    onSuccess: invalidateShopifyConnectionState,
  });
  const syncCatalog = useMutation({
    mutationFn: startCatalogSync,
    onSuccess: async (job) => {
      setSyncJobId(job.id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogStatus }),
        queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogJobs }),
      ]);
    },
  });
  const retryWebhook = useMutation({
    mutationFn: ({ connectionId, eventId }: { connectionId: string; eventId: string }) =>
      retryConnectionEvent(connectionId, eventId),
    onSuccess: async () => {
      if (!shopifyConnection) return;
      await queryClient.invalidateQueries({
        queryKey: integrationManagementQueryKeys.events(shopifyConnection.id),
      });
    },
  });
  const retryDelivery = useMutation({
    mutationFn: ({ connectionId, deliveryId }: { connectionId: string; deliveryId: string }) =>
      retryConnectionDelivery(connectionId, deliveryId),
    onSuccess: async () => {
      if (!shopifyConnection) return;
      await queryClient.invalidateQueries({
        queryKey: integrationManagementQueryKeys.deliveries(shopifyConnection.id),
      });
    },
  });

  async function refreshIntegrationActivity() {
    if (!shopifyConnection) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: integrationManagementQueryKeys.events(shopifyConnection.id) }),
      queryClient.invalidateQueries({ queryKey: integrationManagementQueryKeys.deliveries(shopifyConnection.id) }),
      queryClient.invalidateQueries({ queryKey: integrationManagementQueryKeys.accessAudit(shopifyConnection.id) }),
      queryClient.invalidateQueries({ queryKey: integrationManagementQueryKeys.connectionAudit(shopifyConnection.id) }),
    ]);
  }

  useEffect(() => {
    if (["succeeded", "failed", "cancelled"].includes(syncJob.data?.status ?? "")) {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogStatus }),
        queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogJobs }),
      ]);
    }
  }, [queryClient, syncJob.data?.status]);

  function connect(requestedShop?: string) {
    const normalized = (requestedShop ?? shop).trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/$/, "");
    if (!/^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(normalized)) {
      setValidationMessage("Enter your store's myshopify.com domain, such as example-store.myshopify.com.");
      return;
    }
    // OAuth must be a top-level navigation so Shopify can present its consent screen.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign(`/api/integrations/shopify/connect?shop=${encodeURIComponent(normalized)}`);
  }

  const connected = status.data?.connected;
  const grantedScopes = status.data?.granted_scopes ?? [];
  const effectiveScopes = new Set(grantedScopes);
  if (effectiveScopes.has("write_orders")) effectiveScopes.add("read_orders");
  if (effectiveScopes.has("write_customers")) effectiveScopes.add("read_customers");
  if (effectiveScopes.has("write_products")) effectiveScopes.add("read_products");
  const missingPermissions = REQUIRED_SCOPES.filter(({ scope }) => !effectiveScopes.has(scope));
  const reconnectMessage = missingPermissions.length > 0
    ? `Reconnect Shopify to request: ${missingPermissions.map(({ scope }) => scope).join(", ")}.`
    : "Shopify OAuth configuration is unavailable. Restore the backend OAuth settings before reconnecting.";
  const canManageCatalog = me.data?.role === "owner" || me.data?.role === "admin";
  const syncInProgress = syncJob.data?.status === "queued" || syncJob.data?.status === "running";
  const latestFailedSync = catalog.data?.last_error_code
    ? catalogJobs.data?.items.find(
        (job) => job.status === "failed" && job.last_error_code === catalog.data?.last_error_code,
      )
    : undefined;

  return (
    <Panel>
      <PanelHeader
        title="Shopify"
        description="Connect your store, check permissions, and sync its product catalog."
        action={<span className="grid size-10 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><Store size={19}/></span>}
      />
      <PanelBody className="space-y-5">
        {status.isPending && <div className="h-12 animate-pulse rounded-xl bg-slate-100"/>}
        {status.isError && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{status.error instanceof ApiError ? status.error.message : "Shopify connection status could not be loaded. Refresh to try again."}</p>}
        {status.isSuccess && connected && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50/70 p-4">
          <div><p className="flex items-center gap-2 text-sm font-semibold text-emerald-900"><span className="size-2 rounded-full bg-emerald-500"/>Connected · {status.data.shop_domain}</p><p className="mt-1 text-xs text-emerald-800">{grantedScopes.length} Shopify scope{grantedScopes.length === 1 ? "" : "s"} granted</p></div>
          {confirmDisconnect ? <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Confirm Shopify disconnect">
            <span className="text-xs text-emerald-950">Stored Shopify credentials will be removed.</span>
            <Button type="button" variant="secondary" size="sm" disabled={disconnect.isPending} onClick={() => setConfirmDisconnect(false)}>Keep connected</Button>
            <Button type="button" variant="danger" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}><Unplug size={15}/>{disconnect.isPending ? "Disconnecting…" : "Confirm disconnect"}</Button>
          </div> : <Button type="button" variant="secondary" size="sm" disabled={disconnect.isPending} onClick={() => setConfirmDisconnect(true)}><Unplug size={15}/>Disconnect</Button>}
        </div>}
        {status.data?.reconnect_required && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p role="alert" className="text-sm text-amber-900">{reconnectMessage}</p>
          {status.data.auth_mode === "client_credentials" && status.data.client_credentials_available
            ? <Button type="button" variant="secondary" size="sm" disabled={connectConfigured.isPending} onClick={() => connectConfigured.mutate()}>{connectConfigured.isPending ? "Reconnecting…" : "Reconnect store"}</Button>
            : status.data.auth_mode === "oauth" && status.data.configured && status.data.shop_domain
              ? <Button type="button" variant="secondary" size="sm" onClick={() => connect(status.data?.shop_domain)}><ExternalLink size={15}/>Reauthorize Shopify</Button>
              : null}
        </div>}
        {status.data && !status.data.configured && !status.data.client_credentials_available && <p role="status" className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">For local development, configure a valid store domain, Shopify app client ID and secret, and Fernet encryption key. An HTTPS callback is only needed for Shopify’s browser authorization flow.</p>}
        {!connected && status.data?.client_credentials_available && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50/60 p-4"><div><p className="text-sm font-semibold text-slate-900">Configured demo store</p><p className="mt-1 text-sm text-slate-600">{status.data.configured_store_domain}</p><p className="mt-1 text-xs text-slate-500">Uses server-side app credentials; no browser authorization redirect.</p></div><Button type="button" disabled={connectConfigured.isPending || status.isPending} onClick={() => connectConfigured.mutate()}>{connectConfigured.isPending ? "Connecting…" : "Connect configured store"}</Button></div>}
        {!connected && !status.data?.client_credentials_available && status.data?.configured && <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="block flex-1 space-y-1.5 text-sm font-medium text-slate-700"><span>Shopify store domain</span><Input aria-label="Shopify store domain" placeholder="example-store.myshopify.com" value={shop} onChange={(event) => setShop(event.target.value)} autoComplete="url"/></label>
          <Button type="button" disabled={status.isPending} onClick={() => connect()}><ExternalLink size={16}/>Connect Shopify</Button>
        </div>}
        {validationMessage && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{validationMessage}</p>}
        {disconnect.isError && <p role="alert" className="text-sm text-red-700">{disconnect.error instanceof ApiError ? disconnect.error.message : "The store could not be disconnected."}</p>}
        {connectConfigured.isError && <p role="alert" className="text-sm text-red-700">{connectConfigured.error instanceof ApiError ? connectConfigured.error.message : "The configured store could not be connected."}</p>}

        {status.data?.connected && <section aria-labelledby="shopify-permissions-title" className="space-y-3 rounded-xl border border-slate-200 p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div><h3 id="shopify-permissions-title" className="text-sm font-semibold text-slate-900">Shopify permissions</h3><p className="mt-1 text-xs text-slate-500">Actual grants from the current Shopify installation</p></div>
            <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${effectiveScopes.has("read_products") ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"}`}>
              {effectiveScopes.has("read_products") ? "Product access enabled" : "Product access missing"}
            </span>
          </div>
          {grantedScopes.length > 0 && <div className="flex flex-wrap gap-1.5" aria-label="Scopes granted by Shopify">{grantedScopes.map((scope) => <code key={scope} className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">{scope}</code>)}</div>}
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-100">
            {REQUIRED_SCOPES.map(({ scope, purpose }) => {
              const hasAccess = effectiveScopes.has(scope);
              const inherited = hasAccess && !grantedScopes.includes(scope);
              return <li key={scope} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 text-xs">
                {hasAccess ? <CheckCircle2 aria-hidden="true" size={15} className="text-emerald-600"/> : <AlertTriangle aria-hidden="true" size={15} className="text-amber-600"/>}
                <code className="font-semibold text-slate-800">{scope}</code>
                <span className="min-w-40 flex-1 text-slate-500">{purpose}</span>
                <span className={hasAccess ? "font-medium text-emerald-700" : "font-medium text-amber-800"}>{inherited ? "Included by a write grant" : hasAccess ? "Granted" : "Missing"}</span>
              </li>;
            })}
          </ul>
          {!effectiveScopes.has("read_products") && <p role="status" className="rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-900">Update the Shopify app’s access scopes to include <strong>read_products</strong>, then reconnect the store. Order permissions alone don’t give the AI access to your product catalog.</p>}
        </section>}

        {status.data?.connected && <section aria-labelledby="shopify-capabilities-title" className="space-y-3 rounded-xl border border-slate-200 p-4">
          <div>
            <h3 id="shopify-capabilities-title" className="text-sm font-semibold text-slate-900">Available Shopify features</h3>
            <p className="mt-1 text-xs text-slate-500">Features registered by the backend for this provider.</p>
          </div>
          {providers.isPending && <p role="status" className="text-xs text-slate-500">Loading provider capabilities…</p>}
          {providers.isError && <p role="alert" className="text-xs text-red-700">Shopify feature availability could not be loaded.</p>}
          {providers.isSuccess && shopifyCapabilities.length > 0 && <ul className="flex flex-wrap gap-2">
            {shopifyCapabilities.map((capability) => <li key={capability} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-800">{capability.replaceAll("_", " ")}</li>)}
          </ul>}
          {providers.isSuccess && shopifyCapabilities.length === 0 && <p className="text-xs text-slate-600">No Shopify capabilities are currently registered.</p>}
        </section>}

        {status.data?.connected && <section aria-labelledby="shopify-catalog-title" className="space-y-3 rounded-xl border border-slate-200 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-2"><PackageSearch aria-hidden="true" size={18} className="mt-0.5 text-blue-700"/><div><h3 id="shopify-catalog-title" className="text-sm font-semibold text-slate-900">Product catalog</h3><p className="mt-1 text-xs text-slate-500">Synced products used by storefront recommendations</p></div></div>
            {canManageCatalog && <div className="flex flex-wrap items-end gap-2">
              <label className="space-y-1 text-xs font-medium text-slate-600">
                <span>Sync type</span>
                <select
                  aria-label="Catalog sync type"
                  value={syncMode}
                  onChange={(event) => setSyncMode(event.target.value as CatalogSyncMode)}
                  disabled={syncCatalog.isPending || syncInProgress}
                  className="min-h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-sm text-slate-800"
                >
                  <option value="full">Full refresh</option>
                  <option value="incremental">Changes since last sync</option>
                </select>
              </label>
              <Button type="button" variant="secondary" size="sm" disabled={!catalog.data?.product_scope_granted || syncCatalog.isPending || syncInProgress} onClick={() => syncCatalog.mutate(syncMode)}><RefreshCw size={14} className={syncInProgress ? "animate-spin" : ""}/>{syncInProgress ? "Syncing…" : syncMode === "full" ? "Run full sync" : "Sync changes"}</Button>
            </div>}
          </div>
          {catalog.isPending && <div role="status" className="h-10 animate-pulse rounded-lg bg-slate-100" aria-label="Loading catalog status"/>}
          {catalog.isError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-xs text-red-700">{catalog.error instanceof ApiError ? catalog.error.message : "Catalog status could not be loaded."}</p>}
          {catalog.data && <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-700">
            <p><strong>{catalog.data.product_count}</strong> synced product{catalog.data.product_count === 1 ? "" : "s"}</p>
            <p>{catalog.data.last_sync_at ? `Last successful sync: ${new Date(catalog.data.last_sync_at).toLocaleString("en-US", { timeZone: "UTC", timeZoneName: "short" })}` : "No successful product sync yet"}</p>
          </div>}
          {catalog.data && !catalog.data.product_scope_granted && <p role="status" className="text-xs text-amber-800">Grant <code>read_products</code> before starting a catalog sync.</p>}
          {catalog.data?.product_count === 0 && catalog.data.product_scope_granted && !catalog.data.last_sync_at && <p className="rounded-lg bg-blue-50 p-3 text-xs leading-5 text-blue-900">No products have synced yet. Start a full catalog sync to make products available to the AI widget.</p>}
          {catalog.data?.product_count === 0 && catalog.data.product_scope_granted && catalog.data.last_sync_at && <p className="rounded-lg bg-blue-50 p-3 text-xs leading-5 text-blue-900">The last catalog sync succeeded but Shopify returned no products. Confirm that products exist in the connected store; an empty catalog is a successful sync, not a permissions error.</p>}
          {catalog.data?.last_error_code && <div role="alert" className="space-y-1 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800"><p className="font-semibold">Most recent completed sync failed: <code>{catalog.data.last_error_code}</code></p><p>{catalogSyncGuidance(catalog.data.last_error_code)}</p>{catalog.data.product_count > 0 && <p>{catalog.data.product_count} products from the last successful sync remain available. Last successful sync: {catalog.data.last_sync_at ? new Date(catalog.data.last_sync_at).toLocaleString("en-US", { timeZone: "UTC", timeZoneName: "short" }) : "not recorded"}.</p>}{latestFailedSync?.correlation_id && <p className="text-red-700">Support reference: <SupportTraceLink correlationId={latestFailedSync.correlation_id} /></p>}</div>}
          {syncCatalog.isError && <p role="alert" className="text-xs text-red-700">{syncCatalog.error instanceof ApiError ? syncCatalog.error.message : "Could not start the catalog sync."}</p>}
          {syncJob.data && <p role="status" className="text-xs text-slate-600">Sync status: <strong className="capitalize">{syncJob.data.status}</strong>{syncJob.data.status === "failed" && syncJob.data.last_error_code ? ` · ${syncJob.data.last_error_code}` : ""}</p>}
          {syncJob.isError && <p role="alert" className="text-xs text-red-700">Catalog sync status could not be refreshed.</p>}
          <div className="space-y-2 border-t border-slate-100 pt-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Recent syncs</h4>
            {catalogJobs.isPending && <p role="status" className="text-xs text-slate-500">Loading sync history…</p>}
            {catalogJobs.isError && <p role="alert" className="text-xs text-red-700">Catalog sync history could not be loaded.</p>}
            {catalogJobs.data?.items.length === 0 && <p className="text-xs text-slate-500">No catalog sync jobs have run yet.</p>}
            {catalogJobs.data?.items.map((job) => <div key={job.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs">
              <span className="font-medium capitalize text-slate-800">{job.mode} · {job.status}</span>
              <span className="text-slate-600">{job.records_seen} records · {job.attempt_count}/{job.max_attempts} attempts</span>
              <time className="w-full text-slate-500" dateTime={job.created_at}>{new Date(job.created_at).toLocaleString()}</time>
              {job.last_error_code && <code className="w-full text-red-700">{job.last_error_code}</code>}
              {job.status === "failed" && job.correlation_id && <p className="w-full text-slate-500">Support reference: <SupportTraceLink correlationId={job.correlation_id} /></p>}
            </div>)}
          </div>
        </section>}

        {status.data?.connected && <section aria-labelledby="shopify-activity-title" className="space-y-3 rounded-xl border border-slate-200 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h3 id="shopify-activity-title" className="text-sm font-semibold text-slate-900">Recent integration activity</h3><p className="mt-1 text-xs text-slate-500">Webhook processing and outbound delivery status. Message contents and Shopify payloads are not shown.</p></div>
            <Button type="button" variant="secondary" size="sm" disabled={!shopifyConnection || connectionEvents.isFetching || connectionDeliveries.isFetching || accessAudit.isFetching} onClick={() => void refreshIntegrationActivity()}><RefreshCw size={14} className={connectionEvents.isFetching || connectionDeliveries.isFetching || accessAudit.isFetching ? "animate-spin" : ""}/>Refresh activity</Button>
          </div>
          {connections.isPending && <p role="status" className="text-xs text-slate-500">Loading Shopify connection activity…</p>}
          {connections.isError && <p role="alert" className="text-xs text-red-700">Integration activity could not be loaded.</p>}
          {connections.isSuccess && !shopifyConnection && <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">No active Shopify connection activity is available.</p>}
          {shopifyConnection && <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Incoming events</h4>
              {connectionEvents.isPending && <p role="status" className="text-xs text-slate-500">Loading events…</p>}
              {connectionEvents.isError && <p role="alert" className="text-xs text-red-700">Webhook event history could not be loaded.</p>}
              {connectionEvents.data?.items.length === 0 && <p className="text-xs text-slate-500">No webhook events recorded.</p>}
              {connectionEvents.data?.items.map((event) => <div key={event.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs">
                <span className="font-medium text-slate-800">{event.event_type}</span><span className="capitalize text-slate-600">{event.processing_status} · {event.attempt_count} attempt{event.attempt_count === 1 ? "" : "s"}</span>
                <time className="w-full text-slate-500" dateTime={event.received_at}>{new Date(event.received_at).toLocaleString()}</time>
                {event.last_error_code && <code className="w-full text-red-700">{event.last_error_code}</code>}
                {event.processing_status === "failed" && event.correlation_id && <p className="w-full text-slate-500">Support reference: <SupportTraceLink correlationId={event.correlation_id} /></p>}
                {canManageCatalog && event.manual_retry_available && shopifyConnection && <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="mt-1"
                  disabled={retryWebhook.isPending}
                  onClick={() => retryWebhook.mutate({ connectionId: shopifyConnection.id, eventId: event.id })}
                >Retry event</Button>}
              </div>)}
              {retryWebhook.isError && <p role="alert" className="rounded-lg bg-red-50 p-2 text-xs text-red-700">The webhook event could not be queued. Refresh activity and try again.</p>}
            </div>
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Outbound deliveries</h4>
              {connectionDeliveries.isPending && <p role="status" className="text-xs text-slate-500">Loading deliveries…</p>}
              {connectionDeliveries.isError && <p role="alert" className="text-xs text-red-700">Delivery history could not be loaded.</p>}
              {connectionDeliveries.data?.items.length === 0 && <p className="text-xs text-slate-500">No outbound deliveries recorded.</p>}
              {connectionDeliveries.data?.items.map((delivery) => <div key={delivery.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs">
                <span className="font-medium capitalize text-slate-800">{delivery.status}</span><span className="text-slate-600">{delivery.attempt_count}/{delivery.max_attempts} attempts</span>
                {delivery.manual_retry_count > 0 && <span className="text-slate-500">{delivery.manual_retry_count}/3 manual retries</span>}
                <time className="w-full text-slate-500" dateTime={delivery.created_at}>{new Date(delivery.created_at).toLocaleString()}</time>
                {delivery.last_error_code && <code className="w-full text-red-700">{delivery.last_error_code}</code>}
                {delivery.status === "failed" && delivery.correlation_id && <p className="w-full text-slate-500">Support reference: <SupportTraceLink correlationId={delivery.correlation_id} /></p>}
                {canManageCatalog && delivery.manual_retry_available && shopifyConnection && <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="mt-1"
                  disabled={retryDelivery.isPending}
                  onClick={() => retryDelivery.mutate({ connectionId: shopifyConnection.id, deliveryId: delivery.id })}
                >Retry delivery</Button>}
              </div>)}
              {retryDelivery.isError && <p role="alert" className="rounded-lg bg-red-50 p-2 text-xs text-red-700">The delivery could not be queued. Refresh activity and try again.</p>}
            </div>
          </div>}
        </section>}

        {status.data?.connected && canManageCatalog && <section aria-labelledby="shopify-access-audit-title" className="space-y-3 rounded-xl border border-slate-200 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h3 id="shopify-access-audit-title" className="text-sm font-semibold text-slate-900">Order data access audit</h3><p className="mt-1 text-xs text-slate-500">Shows who accessed Shopify order data and the verification outcome. Customer emails and order numbers are never included.</p></div>
            <Button type="button" variant="secondary" size="sm" disabled={!shopifyConnection || accessAudit.isFetching} onClick={() => void accessAudit.refetch()}><RefreshCw size={14} className={accessAudit.isFetching ? "animate-spin" : ""}/>Refresh audit</Button>
          </div>
          {accessAudit.isPending && <p role="status" className="text-xs text-slate-500">Loading access audit…</p>}
          {accessAudit.isError && <p role="alert" className="text-xs text-red-700">Shopify order access history could not be loaded.</p>}
          {accessAudit.data?.items.length === 0 && <p className="text-xs text-slate-500">No Shopify order access has been recorded.</p>}
          {accessAudit.data?.items.map((entry) => <div key={entry.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs">
            <span className="font-medium text-slate-800">{entry.actor_name} · {entry.resource_type.replaceAll("_", " ")}</span>
            <span className="text-slate-600">{entry.outcome?.replaceAll("_", " ") ?? `${entry.result_count} result${entry.result_count === 1 ? "" : "s"}`}</span>
            <time className="text-slate-500" dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time>
          </div>)}
        </section>}

        {shopifyConnection && canManageCatalog && <section aria-labelledby="shopify-connection-audit-title" className="space-y-3 rounded-xl border border-slate-200 p-4">
          <div><h3 id="shopify-connection-audit-title" className="text-sm font-semibold text-slate-900">Connection lifecycle</h3><p className="mt-1 text-xs text-slate-500">Connection, reauthorization, and disconnect history. Credentials are never recorded.</p></div>
          {connectionAudit.isPending && <p role="status" className="text-xs text-slate-500">Loading connection history…</p>}
          {connectionAudit.isError && <p role="alert" className="text-xs text-red-700">Connection history could not be loaded.</p>}
          {connectionAudit.data?.items.length === 0 && <p className="text-xs text-slate-500">No lifecycle changes have been recorded.</p>}
          {connectionAudit.data?.items.map((entry) => <div key={entry.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs">
            <span className="font-medium capitalize text-slate-800">{entry.event_type} · {entry.provider_id}{entry.actor_name ? ` · ${entry.actor_name}` : " · system"}</span>
            <span className="text-slate-600">{entry.auth_mode ?? "auth mode unavailable"}{entry.granted_scopes.length ? ` · ${entry.granted_scopes.join(", ")}` : ""}</span>
            <time className="text-slate-500" dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time>
          </div>)}
        </section>}

        <div className="flex gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs leading-5 text-slate-600"><ShieldCheck size={17} className="mt-0.5 shrink-0 text-blue-700"/><p>SupportPilot stores credentials server-side. Shopify access tokens and client secrets are never shown here or sent to the browser.</p></div>
        {connected && <p className="flex items-center gap-2 text-xs text-slate-500"><RefreshCw size={13}/>Shopify token refresh is handled securely on the server.</p>}
      </PanelBody>
    </Panel>
  );
}
