import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type WidgetConfig = components["schemas"]["WidgetConfigOut"];
export const widgetConfigKey = ["storefront-widget-config"] as const;

export const getWidgetConfig = () => api<WidgetConfig | null>("/integrations/widget");
export const createWidgetConfig = (config: Pick<WidgetConfig, "allowed_origins" | "ai_enabled" | "ai_reply_mode">) =>
  api<WidgetConfig>("/integrations/widget", {
    method: "POST",
    body: JSON.stringify({ ...config, collect_contact: true }),
  });
export const updateWidgetConfig = (config: Pick<WidgetConfig, "allowed_origins" | "enabled" | "collect_contact" | "ai_enabled" | "ai_reply_mode">) =>
  api<WidgetConfig>("/integrations/widget", {
    method: "PUT",
    body: JSON.stringify(config),
  });
