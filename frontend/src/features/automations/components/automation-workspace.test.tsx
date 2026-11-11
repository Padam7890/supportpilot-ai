import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AutomationWorkspace } from "./automation-workspace";

const mockReplace = vi.fn();
const mockSearchParams = vi.hoisted(() => ({
  get: vi.fn(() => "new"),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace, push: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => mockSearchParams,
}));

const {
  createAutomation,
  getCurrentUser,
  listAutomations,
  previewAutomation,
  updateAutomation,
} = vi.hoisted(() => ({
  createAutomation: vi.fn(),
  getCurrentUser: vi.fn(),
  listAutomations: vi.fn(),
  previewAutomation: vi.fn(),
  updateAutomation: vi.fn(),
}));

vi.mock("../api/automation-api", () => ({
  automationKey: ["automations"],
  createAutomation,
  listAutomations,
  pauseAutomation: vi.fn(),
  publishAutomation: vi.fn(),
  previewAutomation,
  resumeAutomation: vi.fn(),
  restoreAutomationVersion: vi.fn(),
  updateAutomation,
  getAutomationMetrics: vi.fn(),
  listAutomationExecutions: vi.fn(),
  listAutomationVersions: vi.fn(),
}));
vi.mock("@/features/auth/api/auth-api", () => ({ getCurrentUser }));
vi.mock("@/features/organization/api/organization-api", () => ({ listMembers: vi.fn() }));

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Suspense fallback={null}>
        <AutomationWorkspace />
      </Suspense>
    </QueryClientProvider>,
  );
}

describe("automation workspace", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams.get.mockReturnValue("new");
    getCurrentUser.mockResolvedValue({ id: "owner-one", role: "owner" });
    listAutomations.mockResolvedValue([]);
    createAutomation.mockResolvedValue({
      id: "workflow-one",
      name: "Refund triage",
      description: "Prioritize incoming customer conversations using a configured keyword.",
      status: "draft",
      published_version: null,
      draft_version: 1,
      has_unpublished_changes: false,
      definition: {
        trigger: { kind: "customer_message_received", channel: null, first_message_only: false },
        condition_mode: "all",
        conditions: [{ kind: "contains_keyword", value: "refund" }],
        actions: [{ kind: "set_priority", value: "urgent", only_raise: false }],
      },
      canvas_layout: {
        trigger: { x: 400, y: 48 },
        conditions: [{ x: 400, y: 196 }],
        actions: [{ x: 400, y: 344 }],
      },
    });
    previewAutomation.mockResolvedValue({
      matches: true,
      condition_mode: "all",
      conditions: [{ kind: "contains_keyword", label: 'Message contains "refund"', matched: true }],
      planned_actions: [{ kind: "set_priority", summary: "Set ticket priority to urgent", outcome: "would_run" }],
      steps: [
        { step: "Conditions", outcome: "matched", detail: "All conditions matched" },
        { step: "Set priority", outcome: "would_run", detail: "Priority: normal → urgent" },
      ],
    });
  });

  it("creates a customer-message draft with keyword condition and priority action", async () => {
    const { listMembers } = await import("@/features/organization/api/organization-api");
    vi.mocked(listMembers).mockResolvedValue([]);

    renderWorkspace();

    fireEvent.change(await screen.findByLabelText("Workflow name"), { target: { value: "Refund triage" } });
    fireEvent.click(screen.getByText("Message text", { exact: true }));

    const phraseInputs = screen.getAllByLabelText(/message contains/i);
    fireEvent.change(phraseInputs[0]!, { target: { value: "refund" } });

    fireEvent.click(screen.getByRole("button", { name: /save workflow draft/i }));

    await waitFor(() =>
      expect(createAutomation).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Refund triage",
          definition: expect.objectContaining({
            trigger: expect.objectContaining({ kind: "customer_message_received", channel: null, first_message_only: false }),
            condition_mode: "all",
            conditions: [{ kind: "contains_keyword", value: "refund" }],
            actions: [{ kind: "set_priority", value: "high", only_raise: false }],
          }),
          canvas_layout: expect.objectContaining({
            trigger: { x: 400, y: 48 },
            conditions: [{ x: 400, y: 196 }],
            actions: expect.any(Array),
          }),
        }),
      ),
    );
  });

  it("blocks an empty keyword condition from becoming an all-message rule", async () => {
    const { listMembers } = await import("@/features/organization/api/organization-api");
    vi.mocked(listMembers).mockResolvedValue([]);

    renderWorkspace();

    fireEvent.change(await screen.findByLabelText("Workflow name"), { target: { value: "Refund triage" } });
    fireEvent.click(screen.getByText("Message text", { exact: true }));

    expect(screen.getByRole("button", { name: /save workflow draft/i })).toBeDisabled();

    const phraseInputs = screen.getAllByLabelText(/message contains/i);
    fireEvent.change(phraseInputs[0]!, { target: { value: "refund" } });

    expect(screen.getByRole("button", { name: /save workflow draft/i })).not.toBeDisabled();
    expect(createAutomation).not.toHaveBeenCalled();
  });

  it("runs test without persisting the workflow", async () => {
    const { listMembers } = await import("@/features/organization/api/organization-api");
    vi.mocked(listMembers).mockResolvedValue([]);

    renderWorkspace();

    fireEvent.change(await screen.findByLabelText("Workflow name"), { target: { value: "Refund triage" } });

    fireEvent.click(screen.getByText("Message text", { exact: true }));
    const phraseInputs = screen.getAllByLabelText(/message contains/i);
    fireEvent.change(phraseInputs[0]!, { target: { value: "refund" } });

    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    fireEvent.change(screen.getByLabelText("Sample customer message"), {
      target: { value: "I need a refund for my order" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Run test" }));

    await waitFor(() => expect(previewAutomation).toHaveBeenCalled());
    expect(previewAutomation.mock.calls[0]?.[0]).toMatchObject({
      definition: expect.objectContaining({
        trigger: expect.objectContaining({ kind: "customer_message_received", channel: null, first_message_only: false }),
        conditions: [{ kind: "contains_keyword", value: "refund" }],
      }),
      sample_message: "I need a refund for my order",
    });
    expect(await screen.findByText(/Workflow would match/)).toBeInTheDocument();
    expect(createAutomation).not.toHaveBeenCalled();
  });

  it("autosaves edits to an existing draft without publishing", async () => {
    mockSearchParams.get.mockReturnValue("workflow-one");
    const workflow = {
      id: "workflow-one",
      name: "Refund triage",
      description: null,
      status: "draft",
      published_version: null,
      draft_version: 1,
      has_unpublished_changes: false,
      definition: {
        trigger: { kind: "customer_message_received", channel: null, first_message_only: false },
        condition_mode: "all",
        conditions: [{ kind: "contains_keyword", value: "refund" }],
        actions: [{ kind: "set_priority", value: "high", only_raise: false }],
      },
      canvas_layout: {
        trigger: { x: 400, y: 48 },
        conditions: [{ x: 400, y: 196 }],
        actions: [{ x: 400, y: 344 }],
      },
    };
    listAutomations.mockResolvedValue([workflow]);
    updateAutomation.mockResolvedValue({
      ...workflow,
      definition: {
        ...workflow.definition,
        actions: [{ kind: "set_priority" as const, value: "urgent" as const, only_raise: false }],
      },
    });
    const { listMembers } = await import("@/features/organization/api/organization-api");
    vi.mocked(listMembers).mockResolvedValue([]);

    renderWorkspace();

    const actionCard = await screen.findByRole("button", { name: /Configure action 1/ });
    fireEvent.click(actionCard);
    const actionPriority = await screen.findByLabelText("Action priority");
    fireEvent.change(actionPriority, { target: { value: "urgent" } });

    await waitFor(
      () =>
        expect(updateAutomation).toHaveBeenCalledWith(
          workflow.id,
          expect.objectContaining({
            definition: expect.objectContaining({
              actions: [{ kind: "set_priority", value: "urgent", only_raise: false }],
            }),
          }),
        ),
      { timeout: 4000 },
    );
  });

  it("hides builder for viewers", async () => {
    getCurrentUser.mockResolvedValue({ id: "viewer-one", role: "viewer" });
    renderWorkspace();

    expect(await screen.findByText(/owner or admin access/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Workflow name")).not.toBeInTheDocument();
  });
});
