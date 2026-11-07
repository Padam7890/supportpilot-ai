"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert, Plug, RefreshCw } from "lucide-react";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import {
  getIntegrationConnections,
  getIntegrationProviders,
  updateConnectionBotRouting,
  integrationManagementQueryKeys,
  type IntegrationConnection,
  type IntegrationProvider,
} from "../api/integration-management-api";
import { aiAgentsKey, listAIAgents } from "@/features/ai/api/ai-agent-api";
import { Select } from "@/components/ui/input";

const capabilityLabels: Record<string, string> = {
  commerce: "Commerce",
  product_catalog: "Product catalog",
  cart: "Cart",
  checkout: "Checkout",
  webhooks: "Webhooks",
  synchronization: "Catalog sync",
  messaging: "Messaging",
  inbound_messaging: "Inbound messages",
  outbound_messaging: "Outbound messages",
};

export function ProviderOverview() {
  const providers = useQuery({
    queryKey: integrationManagementQueryKeys.providers,
    queryFn: getIntegrationProviders,
  });
  const connections = useQuery({
    queryKey: integrationManagementQueryKeys.connections,
    queryFn: getIntegrationConnections,
  });

  const isLoading = providers.isPending || connections.isPending;
  const isError = providers.isError || connections.isError;

  return (
    <Panel>
      <PanelHeader
        title="Integration capabilities"
        description="Providers are listed when their working adapters are registered."
        action={<span className="grid size-9 place-items-center rounded-xl bg-blue-50 text-blue-700"><Plug size={18} /></span>}
      />
      <PanelBody>
        {isLoading ? (
          <div className="space-y-3" aria-label="Loading integrations">
            <div className="h-20 animate-pulse rounded-xl bg-slate-100" />
            <div className="h-20 animate-pulse rounded-xl bg-slate-100" />
          </div>
        ) : isError ? (
          <div role="alert" className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <CircleAlert size={18} className="mt-0.5 shrink-0" />
            <span>Integration capabilities could not be loaded. Refresh the page to try again.</span>
          </div>
        ) : providers.data?.length ? (
          <div className="space-y-3">
            {providers.data.map((provider) => (
              <ProviderRow
                key={provider.provider_id}
                provider={provider}
                connections={connections.data?.items ?? []}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-300 p-5 text-sm text-slate-600">
            No integration adapters are available yet.
          </div>
        )}
      </PanelBody>
    </Panel>
  );
}

function ProviderRow({
  provider,
  connections,
}: {
  provider: IntegrationProvider;
  connections: IntegrationConnection[];
}) {
  const providerConnections = connections.filter((connection) => connection.provider_id === provider.provider_id);
  const connectedCount = providerConnections.filter((connection) => connection.status === "connected").length;
  const status = connectedCount > 0
    ? `${connectedCount} connected`
    : providerConnections.length > 0
      ? providerConnections[0].status.replaceAll("_", " ")
      : "Not connected";

  return (
    <article className="rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${connectedCount ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
            {connectedCount ? <CheckCircle2 size={19} /> : <Plug size={19} />}
          </span>
          <div className="min-w-0">
            <h3 className="font-semibold text-slate-900">{provider.display_name}</h3>
            <p className="mt-0.5 text-xs text-slate-500">Provider v{provider.version}</p>
          </div>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${connectedCount ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
          {status}
        </span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2" aria-label={`${provider.display_name} capabilities`}>
        {provider.capabilities.map((capability) => (
          <span key={capability} className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-800">
            {capabilityLabels[capability] ?? capability.replaceAll("_", " ")}
          </span>
        ))}
      </div>
      {providerConnections.some((connection) => connection.status === "error" || connection.status === "reauthorization_required") && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-amber-800">
          <RefreshCw size={13} /> Review the connection below to restore provider access.
        </p>
      )}
      {provider.capabilities.includes("inbound_messaging") && (
        <div className="mt-4 space-y-3 border-t border-slate-100 pt-4">
          <p className="text-xs text-slate-500">Choose the AI bot for new conversations from this channel. Existing conversations keep their current bot.</p>
          {providerConnections.filter((connection) => connection.status === "connected").map((connection) => (
            <ConnectionBotRouting key={connection.id} connection={connection}/>
          ))}
          {providerConnections.every((connection) => connection.status !== "connected") && (
            <p className="text-xs text-slate-500">Connect an account before configuring its AI bot.</p>
          )}
        </div>
      )}
    </article>
  );
}

function ConnectionBotRouting({ connection }: { connection: IntegrationConnection }) {
  const queryClient = useQueryClient();
  const bots = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents });
  const update = useMutation({
    mutationFn: (aiAgentId: string | null) => updateConnectionBotRouting(connection.id, aiAgentId),
    onSuccess: async (saved) => {
      queryClient.setQueryData<Awaited<ReturnType<typeof getIntegrationConnections>>>(
        integrationManagementQueryKeys.connections,
        (current) => current && ({ ...current, items: current.items.map((item) => item.id === saved.id ? saved : item) }),
      );
      await queryClient.invalidateQueries({ queryKey: integrationManagementQueryKeys.connectionAudit(connection.id) });
    },
  });
  const activeBots = bots.data?.items.filter((bot) => bot.status === "active") ?? [];

  return (
    <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(220px,0.8fr)] sm:items-center">
      <label htmlFor={`connection-bot-${connection.id}`} className="text-sm font-medium text-slate-700">{connection.display_name} · incoming bot</label>
      <Select
        id={`connection-bot-${connection.id}`}
        value={connection.ai_agent_id ?? ""}
        disabled={bots.isPending || bots.isError || update.isPending || activeBots.length === 0}
        onChange={(event) => update.mutate(event.target.value || null)}
      >
        <option value="">Use workspace default bot</option>
        {activeBots.map((bot) => <option key={bot.id} value={bot.id}>{bot.name}{bot.is_default ? " · default" : ""}</option>)}
      </Select>
      {bots.isError && <p role="alert" className="text-xs text-red-700 sm:col-span-2">AI bots could not be loaded for this connection.</p>}
      {update.isError && <p role="alert" className="text-xs text-red-700 sm:col-span-2">Bot routing could not be saved. Try again.</p>}
      {update.isSuccess && <p role="status" className="text-xs text-emerald-700 sm:col-span-2">New conversations will use the selected routing.</p>}
    </div>
  );
}
