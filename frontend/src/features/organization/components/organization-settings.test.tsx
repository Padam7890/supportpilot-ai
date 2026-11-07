import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OrganizationSettings from "./organization-settings";

const { getCurrentUser, getOrganization, listMembers, listInvitations } = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  getOrganization: vi.fn(),
  listMembers: vi.fn(),
  listInvitations: vi.fn(),
}));

vi.mock("@/features/auth/api/auth-api", () => ({ getCurrentUser }));
vi.mock("../api/organization-api", () => ({
  getOrganization,
  listMembers,
  listInvitations,
  createInvitation: vi.fn(),
  revokeInvitation: vi.fn(),
  updateMember: vi.fn(),
  updateOrganization: vi.fn(),
}));
vi.mock("@/features/auth/components/security-sessions", () => ({ SecuritySessions: () => <div>Session controls</div> }));
vi.mock("@/features/integrations/components/shopify-integration-card", () => ({ ShopifyIntegrationCard: () => <div>Shopify configuration</div> }));
vi.mock("@/features/integrations/components/storefront-widget-card", () => ({ StorefrontWidgetCard: () => <div>Widget configuration</div> }));
vi.mock("@/features/recommendations/components/recommendation-settings-card", () => ({ RecommendationSettingsCard: () => <div>Recommendation configuration</div> }));

function renderSettings() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><OrganizationSettings/></QueryClientProvider>);
}

describe("organization settings navigation", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, "", "/dashboard/settings");
    getCurrentUser.mockResolvedValue({ id: "user-1", role: "owner" });
    getOrganization.mockResolvedValue({ name: "SupportPilot", slug: "supportpilot" });
    listMembers.mockResolvedValue([]);
    listInvitations.mockResolvedValue([]);
  });

  it("restores a direct section link and updates the URL when navigating", async () => {
    window.history.replaceState(null, "", "/dashboard/settings#widget");
    renderSettings();

    expect(await screen.findByRole("heading", { name: "Chat widget" })).toBeInTheDocument();
    expect(screen.getByText("Widget configuration")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));
    expect(await screen.findByRole("heading", { name: "Integrations" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#shopify");
  });

  it("keeps members-only data queries disabled for a Viewer opening a restricted hash", async () => {
    getCurrentUser.mockResolvedValue({ id: "user-2", role: "viewer" });
    window.history.replaceState(null, "", "/dashboard/settings#team");
    renderSettings();

    expect(await screen.findByRole("heading", { name: "Security" })).toBeInTheDocument();
    await waitFor(() => expect(listMembers).not.toHaveBeenCalled());
    expect(listInvitations).not.toHaveBeenCalled();
  });
});
