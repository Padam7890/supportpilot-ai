import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StorefrontWidgetCard } from "./storefront-widget-card";

const { createWidgetConfig, getWidgetConfig, listAIAgents, updateWidgetConfig } = vi.hoisted(() => ({
  createWidgetConfig: vi.fn(),
  getWidgetConfig: vi.fn(),
  listAIAgents: vi.fn(),
  updateWidgetConfig: vi.fn(),
}));

vi.mock("../api/widget-api", () => ({
  createWidgetConfig,
  getWidgetConfig,
  updateWidgetConfig,
  previewWidgetRouting: vi.fn(),
  widgetConfigKey: ["storefront-widget-config"],
}));
vi.mock("@/features/ai/api/ai-agent-api", () => ({
  aiAgentsKey: ["ai-agents"],
  listAIAgents,
}));

const config = {
  public_id: "widget-public-identifier-123456",
  ai_agent_id: "bot-returns",
  ai_agent_ids: ["bot-returns"],
  allowed_origins: ["https://shop.example"],
  enabled: true,
  collect_contact: true,
  ai_enabled: true,
  ai_reply_mode: "draft_only" as const,
  created_at: "2026-11-06T00:00:00Z",
};

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><StorefrontWidgetCard/></QueryClientProvider>);
}

describe("storefront widget bot configuration", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    getWidgetConfig.mockResolvedValue(config);
    listAIAgents.mockResolvedValue({
      items: [
        { id: "bot-returns", name: "Returns bot", status: "active", is_default: true },
        { id: "bot-shipping", name: "Shipping bot", status: "active", is_default: false },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    });
    updateWidgetConfig.mockResolvedValue({ ...config, ai_agent_ids: ["bot-returns", "bot-shipping"] });
  });

  it("saves several enabled bots as the widget's routing allowlist", async () => {
    renderCard();
    const shippingBot = await screen.findByRole("checkbox", { name: "Use Shipping bot in widget" });
    const input = shippingBot.parentElement?.querySelector<HTMLInputElement>('input[type="checkbox"]');
    expect(input).toBeTruthy();
    fireEvent.click(input!);
    await waitFor(() => expect(shippingBot).toBeChecked());
    fireEvent.click(screen.getByRole("button", { name: "Save widget settings" }));

    await waitFor(() => expect(updateWidgetConfig).toHaveBeenCalledWith(expect.objectContaining({
      ai_agent_id: "bot-returns",
      ai_agent_ids: ["bot-returns", "bot-shipping"],
    })));
  });
});
