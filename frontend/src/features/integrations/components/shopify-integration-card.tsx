"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, RefreshCw, ShieldCheck, Store, Unplug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ApiError } from "@/lib/api/errors";
import { connectConfiguredShopifyStore, disconnectShopify, getShopifyStatus, shopifyQueryKeys } from "../api/shopify-api";

export function ShopifyIntegrationCard() {
  const queryClient = useQueryClient();
  const [shop, setShop] = useState("");
  const [validationMessage, setValidationMessage] = useState<string>();
  const status = useQuery({ queryKey: shopifyQueryKeys.status, queryFn: getShopifyStatus });
  const disconnect = useMutation({
    mutationFn: disconnectShopify,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.status }),
  });
  const connectConfigured = useMutation({
    mutationFn: connectConfiguredShopifyStore,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: shopifyQueryKeys.status }),
  });

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
  return (
    <Panel>
      <PanelHeader
        title="Shopify"
        description="Sync customer context and look up verified orders and tracking."
        action={<span className="grid size-10 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><Store size={19}/></span>}
      />
      <PanelBody className="space-y-5">
        {status.isPending && <div className="h-12 animate-pulse rounded-xl bg-slate-100"/>}
        {status.isError && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">Shopify connection status could not be loaded. Refresh to try again.</p>}
        {status.isSuccess && connected && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50/70 p-4">
          <div><p className="flex items-center gap-2 text-sm font-semibold text-emerald-900"><span className="size-2 rounded-full bg-emerald-500"/>Connected · {status.data.shop_domain}</p><p className="mt-1 text-xs text-emerald-800">Granted access: {(status.data.granted_scopes ?? []).join(", ")}</p></div>
          <Button variant="secondary" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}><Unplug size={15}/>{disconnect.isPending ? "Disconnecting…" : "Disconnect"}</Button>
        </div>}
        {status.data?.reconnect_required && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Reconnect Shopify to grant both read_orders and read_customers scopes.</p>}
        {status.data && !status.data.configured && !status.data.client_credentials_available && <p role="status" className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">For local development, configure a valid store domain, Shopify app client ID and secret, and Fernet encryption key. An HTTPS callback is only needed for Shopify’s browser authorization flow.</p>}
        {!connected && status.data?.client_credentials_available && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50/60 p-4"><div><p className="text-sm font-semibold text-slate-900">Configured demo store</p><p className="mt-1 text-sm text-slate-600">{status.data.configured_store_domain}</p><p className="mt-1 text-xs text-slate-500">Uses server-side app credentials; no browser authorization redirect.</p></div><Button type="button" disabled={connectConfigured.isPending || status.isPending} onClick={() => connectConfigured.mutate()}>{connectConfigured.isPending ? "Connecting…" : "Connect configured store"}</Button></div>}
        {!connected && !status.data?.client_credentials_available && status.data?.configured && <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="block flex-1 space-y-1.5 text-sm font-medium text-slate-700"><span>Shopify store domain</span><Input aria-label="Shopify store domain" placeholder="example-store.myshopify.com" value={shop} onChange={(event) => setShop(event.target.value)} autoComplete="url"/></label>
          <Button type="button" disabled={status.isPending} onClick={connect}><ExternalLink size={16}/>Connect Shopify</Button>
        </div>}
        {validationMessage && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{validationMessage}</p>}
        {disconnect.isError && <p role="alert" className="text-sm text-red-700">{disconnect.error instanceof ApiError ? disconnect.error.message : "The store could not be disconnected."}</p>}
        {connectConfigured.isError && <p role="alert" className="text-sm text-red-700">{connectConfigured.error instanceof ApiError ? connectConfigured.error.message : "The configured store could not be connected."}</p>}
        <div className="flex gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs leading-5 text-slate-600"><ShieldCheck size={17} className="mt-0.5 shrink-0 text-blue-700"/><p>Read-only access only. SupportPilot asks for <strong>read_orders</strong> and <strong>read_customers</strong>. Shopify may separately require protected customer-data approval before names or email addresses are available. Refunds, cancellations, and order changes are not enabled.</p></div>
        {connected && <p className="flex items-center gap-2 text-xs text-slate-500"><RefreshCw size={13}/>Access credentials rotate securely on the server and never enter browser storage.</p>}
      </PanelBody>
    </Panel>
  );
}
