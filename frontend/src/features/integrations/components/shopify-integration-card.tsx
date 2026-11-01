"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ExternalLink, PackageSearch, RefreshCw, ShieldCheck, Store, Unplug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getCurrentUser, currentUserQueryKey } from "@/features/auth/api/auth-api";
import { ApiError } from "@/lib/api/errors";
import {
  connectConfiguredShopifyStore,
  disconnectShopify,
  getCatalogStatus,
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

export function ShopifyIntegrationCard() {
  const queryClient = useQueryClient();
  const [shop, setShop] = useState("");
  const [syncJobId, setSyncJobId] = useState<string>();
  const [validationMessage, setValidationMessage] = useState<string>();
  const status = useQuery({ queryKey: shopifyQueryKeys.status, queryFn: getShopifyStatus });
  const catalog = useQuery({
    queryKey: shopifyQueryKeys.catalogStatus,
    queryFn: getCatalogStatus,
    enabled: Boolean(status.data?.connected),
  });
  const me = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
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
  const disconnect = useMutation({
    mutationFn: disconnectShopify,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.status });
      await queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogStatus });
    },
  });
  const connectConfigured = useMutation({
    mutationFn: connectConfiguredShopifyStore,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.status }),
  });
  const syncCatalog = useMutation({
    mutationFn: startCatalogSync,
    onSuccess: async (job) => {
      setSyncJobId(job.id);
      await queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogStatus });
    },
  });

  useEffect(() => {
    if (["succeeded", "failed", "cancelled"].includes(syncJob.data?.status ?? "")) {
      void queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.catalogStatus });
    }
  }, [queryClient, syncJob.data?.status]);

  function connect() {
    const normalized = shop.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/$/, "");
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
  const canManageCatalog = me.data?.role === "owner" || me.data?.role === "admin";
  const syncInProgress = syncJob.data?.status === "queued" || syncJob.data?.status === "running";

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
          <Button variant="secondary" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}><Unplug size={15}/>{disconnect.isPending ? "Disconnecting…" : "Disconnect"}</Button>
        </div>}
        {status.data?.reconnect_required && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Reconnect Shopify to restore its required order and customer permissions.</p>}
        {status.data && !status.data.configured && !status.data.client_credentials_available && <p role="status" className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">For local development, configure a valid store domain, Shopify app client ID and secret, and Fernet encryption key. An HTTPS callback is only needed for Shopify’s browser authorization flow.</p>}
        {!connected && status.data?.client_credentials_available && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50/60 p-4"><div><p className="text-sm font-semibold text-slate-900">Configured demo store</p><p className="mt-1 text-sm text-slate-600">{status.data.configured_store_domain}</p><p className="mt-1 text-xs text-slate-500">Uses server-side app credentials; no browser authorization redirect.</p></div><Button type="button" disabled={connectConfigured.isPending || status.isPending} onClick={() => connectConfigured.mutate()}>{connectConfigured.isPending ? "Connecting…" : "Connect configured store"}</Button></div>}
        {!connected && !status.data?.client_credentials_available && status.data?.configured && <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="block flex-1 space-y-1.5 text-sm font-medium text-slate-700"><span>Shopify store domain</span><Input aria-label="Shopify store domain" placeholder="example-store.myshopify.com" value={shop} onChange={(event) => setShop(event.target.value)} autoComplete="url"/></label>
          <Button type="button" disabled={status.isPending} onClick={connect}><ExternalLink size={16}/>Connect Shopify</Button>
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

        {status.data?.connected && <section aria-labelledby="shopify-catalog-title" className="space-y-3 rounded-xl border border-slate-200 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-2"><PackageSearch aria-hidden="true" size={18} className="mt-0.5 text-blue-700"/><div><h3 id="shopify-catalog-title" className="text-sm font-semibold text-slate-900">Product catalog</h3><p className="mt-1 text-xs text-slate-500">Synced products used by storefront recommendations</p></div></div>
            {canManageCatalog && <Button type="button" variant="secondary" size="sm" disabled={!catalog.data?.product_scope_granted || syncCatalog.isPending || syncInProgress} onClick={() => syncCatalog.mutate()}><RefreshCw size={14} className={syncInProgress ? "animate-spin" : ""}/>{syncInProgress ? "Syncing…" : "Sync catalog"}</Button>}
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
          {catalog.data?.last_error_code && <p role="alert" className="text-xs text-red-700">Latest sync issue: <code>{catalog.data.last_error_code}</code></p>}
          {syncCatalog.isError && <p role="alert" className="text-xs text-red-700">{syncCatalog.error instanceof ApiError ? syncCatalog.error.message : "Could not start the catalog sync."}</p>}
          {syncJob.data && <p role="status" className="text-xs text-slate-600">Sync status: <strong className="capitalize">{syncJob.data.status}</strong>{syncJob.data.status === "failed" && syncJob.data.last_error_code ? ` · ${syncJob.data.last_error_code}` : ""}</p>}
          {syncJob.isError && <p role="alert" className="text-xs text-red-700">Catalog sync status could not be refreshed.</p>}
        </section>}

        <div className="flex gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs leading-5 text-slate-600"><ShieldCheck size={17} className="mt-0.5 shrink-0 text-blue-700"/><p>SupportPilot stores credentials server-side. Shopify access tokens and client secrets are never shown here or sent to the browser.</p></div>
        {connected && <p className="flex items-center gap-2 text-xs text-slate-500"><RefreshCw size={13}/>Shopify token refresh is handled securely on the server.</p>}
      </PanelBody>
    </Panel>
  );
}
