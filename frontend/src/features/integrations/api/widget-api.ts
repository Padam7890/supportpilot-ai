import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type WidgetConfig = components["schemas"]["WidgetConfigOut"];
export type WidgetRoutingPreview = components["schemas"]["WidgetRoutingPreviewOut"];
export const widgetConfigKey = ["storefront-widget-config"] as const;

export const getWidgetConfig = () => api<WidgetConfig | null>("/integrations/widget");
export const createWidgetConfig = (config: Pick<WidgetConfig, "allowed_origins" | "ai_enabled" | "ai_reply_mode"> & { ai_agent_id?: string; ai_agent_ids?: string[] }) =>
  api<WidgetConfig>("/integrations/widget", {
    method: "POST",
    body: JSON.stringify({ ...config, collect_contact: true }),
  });
export const updateWidgetConfig = (config: Pick<WidgetConfig, "allowed_origins" | "enabled" | "collect_contact" | "ai_enabled" | "ai_reply_mode"> & { ai_agent_id?: string; ai_agent_ids?: string[] }) =>
  api<WidgetConfig>("/integrations/widget", {
    method: "PUT",
    body: JSON.stringify(config),
  });
export const previewWidgetRouting = (input: { message: string; ai_agent_ids: string[] }) =>
  api<WidgetRoutingPreview>("/integrations/widget/routing-preview", {
    method: "POST",
    body: JSON.stringify(input),
  });
