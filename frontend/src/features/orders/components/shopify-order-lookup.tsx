"use client";

import { useEffect, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { ArrowLeft, ArrowRight, ExternalLink, PackageSearch, ShieldCheck, Truck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/utils";
import { getShopifyOrders, getShopifyStatus } from "@/features/integrations/api/shopify-api";
import { getVerifiedShopifyOrder, getVerifiedShopifyOrders, shopifyQueryKeys } from "@/features/integrations/api/shopify-api";
import type { ShopifyOrder, ShopifyOrderLookup } from "@/features/integrations/api/shopify-api";
import { shopifyLookupSchema, type ShopifyLookupValues } from "../schemas/shopify-order.schema";

export function ShopifyOrderLookup() {
  const [lookupValues, setLookupValues] = useState<ShopifyLookupValues>();
  const [result, setResult] = useState<ShopifyOrderLookup>();
  const [selected, setSelected] = useState<ShopifyOrder>();
  const status = useQuery({ queryKey: shopifyQueryKeys.status, queryFn: getShopifyStatus });
  const orders = useInfiniteQuery({
    queryKey: shopifyQueryKeys.orderPages(),
    queryFn: ({ pageParam }) => getShopifyOrders({ cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: status.data?.connected === true,
  });
  const orderRows = orders.data?.pages.flatMap((page) => page.items) ?? [];
  const form = useForm<ShopifyLookupValues>({ resolver: zodResolver(shopifyLookupSchema), defaultValues: { customer_email: "", order_number: "" } });
  const lookup = useMutation({
    mutationFn: (values: ShopifyLookupValues & { cursor?: string }) => getVerifiedShopifyOrders(values),
    onSuccess: (data) => { setResult(data); setSelected(data.matched_order); },
  });
  const detail = useMutation({
    mutationFn: ({ orderNumber, email }: { orderNumber: string; email: string }) => getVerifiedShopifyOrder(orderNumber, email),
    onSuccess: setSelected,
  });

  useEffect(() => {
    const email = new URLSearchParams(window.location.search).get("email");
    if (email) form.setValue("customer_email", email);
  }, [form]);

  function submit(values: ShopifyLookupValues) {
    setLookupValues(values);
    setResult(undefined);
    setSelected(undefined);
    lookup.mutate(values);
  }

  const disconnected = status.data && !status.data.connected;
  const configuredStoreAvailable = status.data?.client_credentials_available;
  const oauthAvailable = status.data?.configured;
  const canConnectFromSettings = configuredStoreAvailable || oauthAvailable;
  return <div className="space-y-6">
    <header><p className="text-sm font-semibold text-blue-700">Read-only integration</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Shopify orders</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Verify the customer with both their Shopify order number and email before viewing order, payment, fulfillment, or tracking details.</p></header>
    {status.isPending && <div className="h-16 animate-pulse rounded-2xl bg-slate-100"/>}
    {status.isError && <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">Shopify connection status could not be checked.</p>}
    {disconnected && <Panel><PanelBody className="flex flex-wrap items-center justify-between gap-4 p-5"><div><h2 className="font-semibold">{configuredStoreAvailable ? "Connect the configured Shopify store" : oauthAvailable ? "Connect a Shopify store" : "Shopify setup is incomplete"}</h2><p className="mt-1 text-sm text-slate-500">{configuredStoreAvailable ? "An Owner or Admin can connect the configured development store from Settings → Integrations. This local flow does not need an HTTPS callback." : oauthAvailable ? "An Owner or Admin can connect the workspace store in Settings → Integrations." : "For the local configured-store flow, set a valid store domain, Shopify app client ID and secret, and encryption key on the backend. An HTTPS callback is only needed for Shopify's browser authorization flow."}</p></div>{canConnectFromSettings && <a href="/dashboard/settings#integrations" className="inline-flex items-center gap-2 text-sm font-semibold text-blue-700 hover:underline">Open integrations <ExternalLink size={15}/></a>}</PanelBody></Panel>}
    {status.data?.connected && <>
      <Panel>
        <PanelHeader title="Store orders" description="Recent orders from your connected Shopify store. Customer details are omitted from this list."/>
        <PanelBody>
          {orders.isPending && <div role="status" aria-label="Loading Shopify orders" className="space-y-3">{[1, 2, 3].map((row) => <div key={row} className="h-14 animate-pulse rounded-lg bg-slate-100"/>)}</div>}
          {orders.isError && <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700"><p>Could not load Shopify orders. {orders.error instanceof ApiError ? orders.error.message : "Check the Shopify connection and try again."}</p>{orders.error instanceof ApiError && <p className="mt-1 text-xs text-red-600">API status {orders.error.status}{orders.error.code ? ` · ${orders.error.code}` : ""}</p>}<Button variant="unstyled" type="button" className="mt-2 font-semibold underline" onClick={() => orders.refetch()}>Try again</Button></div>}
          {!orders.isPending && !orders.isError && orderRows.length === 0 && <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center"><p className="font-semibold text-slate-800">No orders found</p><p className="mt-1 text-sm text-slate-500">Orders from the connected store will appear here.</p></div>}
          {orderRows.length > 0 && <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <caption className="sr-only">Shopify orders from the connected store</caption>
              <thead><tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500"><th scope="col" className="px-3 py-3">Order</th><th scope="col" className="px-3 py-3">Date</th><th scope="col" className="px-3 py-3">Payment</th><th scope="col" className="px-3 py-3">Fulfillment</th><th scope="col" className="px-3 py-3 text-right">Total</th></tr></thead>
              <tbody>{orderRows.map((order) => <tr key={order.id} className="border-b border-slate-100 last:border-0"><th scope="row" className="px-3 py-3 font-semibold text-slate-900">{order.order_number}</th><td className="whitespace-nowrap px-3 py-3 text-slate-600">{formatDateTime(order.created_at)}</td><td className="px-3 py-3 text-slate-600">{titleCase(order.financial_status ?? "unknown")}</td><td className="px-3 py-3 text-slate-600">{titleCase(order.fulfillment_status ?? "unknown")}</td><td className="whitespace-nowrap px-3 py-3 text-right font-medium text-slate-900">{order.total_amount} {order.currency}</td></tr>)}</tbody>
            </table>
          </div>}
          {orders.hasNextPage && <div className="mt-4 flex justify-center"><Button type="button" variant="secondary" onClick={() => orders.fetchNextPage()} disabled={orders.isFetchingNextPage}>{orders.isFetchingNextPage ? "Loading…" : "Load more orders"}<ArrowRight size={15}/></Button></div>}
        </PanelBody>
      </Panel>
      <Panel><PanelHeader title="Verify a Shopify customer" description={`Connected store: ${status.data.shop_domain ?? "Shopify"}`}/><PanelBody>
        <form className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end" onSubmit={form.handleSubmit(submit)}>
          <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Customer email</span><Input type="email" autoComplete="email" aria-invalid={Boolean(form.formState.errors.customer_email)} {...form.register("customer_email")}/>{form.formState.errors.customer_email && <span className="text-xs font-normal text-red-700">{form.formState.errors.customer_email.message}</span>}</label>
          <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Shopify order number</span><Input aria-label="Shopify order number" placeholder="#1042" aria-invalid={Boolean(form.formState.errors.order_number)} {...form.register("order_number")}/>{form.formState.errors.order_number && <span className="text-xs font-normal text-red-700">{form.formState.errors.order_number.message}</span>}</label>
          <Button type="submit" disabled={lookup.isPending}><PackageSearch size={16}/>{lookup.isPending ? "Verifying…" : "Verify and find orders"}</Button>
        </form>
        <p className="mt-4 flex items-start gap-2 rounded-xl bg-blue-50 p-3 text-xs leading-5 text-blue-900"><ShieldCheck size={15} className="mt-0.5 shrink-0"/>Order data stays hidden unless Shopify confirms that the order number and customer email match.</p>
        {lookup.isError && <p role="alert" className="mt-3 text-sm text-red-700">{lookup.error instanceof ApiError ? lookup.error.message : "Shopify could not verify this customer right now."}</p>}
      </PanelBody></Panel>
      {result && <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.75fr)]">
        <Panel><PanelHeader title="Verified customer order history" description={`${result.customer.display_name ?? result.customer.email} · verified by order number and email`}/><PanelBody className="space-y-2">
          {result.recent_orders.map((order) => <Button variant="unstyled" key={order.id} type="button" className={`w-full rounded-xl border p-4 text-left transition hover:border-blue-300 hover:bg-blue-50/40 ${selected?.id === order.id ? "border-blue-400 bg-blue-50/60" : "border-slate-200"}`} onClick={() => { setSelected(undefined); detail.mutate({ orderNumber: order.order_number, email: result.customer.email }); }}>
            <span className="flex flex-wrap items-center justify-between gap-3"><span><span className="block font-semibold text-slate-900">{order.order_number}</span><span className="mt-1 block text-xs text-slate-500">{formatDateTime(order.created_at)}</span></span><span className="text-right"><span className="block font-semibold text-slate-900">{order.total_amount} {order.currency}</span><span className="mt-1 block text-xs capitalize text-slate-500">{titleCase(order.financial_status ?? "unknown")} · {titleCase(order.fulfillment_status ?? "unknown")}</span></span></span>
          </Button>)}
          {result.recent_orders.length === 0 && <p className="rounded-xl border border-dashed p-5 text-sm text-slate-500">This verified customer has no recent orders.</p>}
          {result.has_next_page && result.next_cursor && lookupValues && <Button variant="secondary" onClick={() => lookup.mutate({ ...lookupValues, cursor: result.next_cursor ?? undefined })} disabled={lookup.isPending}>More orders <ArrowRight size={15}/></Button>}
          {lookup.isPending && <p role="status" className="text-xs text-slate-500">Loading the next page…</p>}
        </PanelBody></Panel>
        <Panel><PanelHeader title="Order details" description="Payment and fulfillment status from Shopify" action={<Truck size={17} className="text-slate-400"/>}/><PanelBody>
          {detail.isPending && <div className="h-36 animate-pulse rounded-xl bg-slate-100"/>}
          {detail.isError && <p role="alert" className="text-sm text-red-700">Order details could not be loaded.</p>}
          {selected && <div className="space-y-4">
            <div><p className="text-2xl font-bold">{selected.order_number}</p><p className="mt-1 text-sm text-slate-500">Placed {formatDateTime(selected.created_at)}</p></div>
            <dl className="grid grid-cols-2 gap-3 text-sm"><Detail label="Total" value={`${selected.total_amount} ${selected.currency}`}/><Detail label="Payment" value={titleCase(selected.financial_status ?? "unknown")}/><Detail label="Fulfillment" value={titleCase(selected.fulfillment_status ?? "unknown")}/></dl>
            <div><h3 className="text-sm font-semibold">Tracking</h3>{selected.tracking.length ? <ul className="mt-2 space-y-2">{selected.tracking.map((track, index) => <li key={`${track.number}-${index}`} className="rounded-lg bg-slate-50 p-3 text-sm"><p className="font-medium">{track.company ?? "Carrier"} · {track.number ?? "Tracking pending"}</p>{track.url && <a href={track.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-blue-700 hover:underline">Track shipment <ExternalLink size={12}/></a>}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No tracking information available.</p>}</div>
          </div>}
          {!selected && !detail.isPending && <p className="text-sm text-slate-500">Select an order to view its details.</p>}
        </PanelBody></Panel>
      </div>}
    </>}
    <a href="/dashboard/inbox" className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-blue-700"><ArrowLeft size={15}/>Back to inbox</a>
  </div>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-slate-50 p-3"><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 font-semibold text-slate-900">{value}</dd></div>;
}

function titleCase(value: string) {
  return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
