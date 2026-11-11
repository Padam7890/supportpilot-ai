import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AnalyticsDashboard } from "./analytics-dashboard";

const { getAIUsage, getEvaluationSummary, getIntegrationDeliveryAnalytics, getAutomationMetrics, submitEvaluation, listAIExecutions } = vi.hoisted(() => ({
  getAIUsage: vi.fn(),
  getEvaluationSummary: vi.fn(),
  getIntegrationDeliveryAnalytics: vi.fn(),
  getAutomationMetrics: vi.fn(),
  submitEvaluation: vi.fn(),
  listAIExecutions: vi.fn(),
}));

vi.mock("../api/analytics-api", () => ({
  analyticsQueryKeys: {
    usage: (start: string, end: string) => ["usage", start, end],
    evaluations: (start: string, end: string) => ["evaluations", start, end],
    supportResponses: (start: string, end: string) => ["responses", start, end],
    commerceApprovals: (start: string, end: string) => ["approvals", start, end],
    integrationDeliveries: (start: string, end: string) => ["deliveries", start, end],
  },
  getSupportResponseAnalytics: vi.fn().mockResolvedValue({ conversations: 0, daily: [] }),
  getCommerceApprovalAnalytics: vi.fn().mockResolvedValue({ total: 0 }),
  getAIUsage,
  getEvaluationSummary,
  getIntegrationDeliveryAnalytics,
  submitEvaluation,
}));
vi.mock("@/features/ai/api/ai-api", () => ({ listAIExecutions }));
vi.mock("@/features/automations/api/automation-api", () => ({
  automationKey: ["automations"],
  getAutomationMetrics,
}));

describe("analytics dashboard", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    vi.clearAllMocks();
    getAIUsage.mockResolvedValue({
      start_date: "2026-10-02", end_date: "2026-10-31", executions: 1, succeeded: 1, failed: 0,
      prompt_tokens: 20, completion_tokens: 12, total_tokens: 32, estimated_cost_usd: null,
      daily: [{ date: "2026-10-31", executions: 1, prompt_tokens: 20, completion_tokens: 12 }],
    });
    getEvaluationSummary.mockResolvedValue({
      start_date: "2026-10-02", end_date: "2026-10-31", rated: 0, helpful: 0,
      not_helpful: 0, helpful_rate: null, by_category: {},
    });
    getIntegrationDeliveryAnalytics.mockResolvedValue({
      start_date: "2026-10-02", end_date: "2026-10-31", total: 2, succeeded: 1, failed: 1,
      queued: 0, running: 0, cancelled: 0, average_attempts: 1.5,
      providers: [{ provider_id: "example_chat", total: 2, succeeded: 1, failed: 1 }],
      daily: [{ date: "2026-10-31", total: 2, succeeded: 1, failed: 1, queued: 0, running: 0, cancelled: 0 }],
      top_errors: [{ code: "provider_timeout", count: 1 }],
    });
    getAutomationMetrics.mockResolvedValue({
      window_start: "2026-10-01T00:00:00Z", window_end: "2026-10-31T00:00:00Z",
      total: 8, queued: 1, running: 1, succeeded: 5, failed: 1, average_duration_ms: 42,
      daily: [{ date: "2026-10-31", total: 8, succeeded: 5, failed: 1, queued: 1, running: 1 }],
      top_errors: [{ code: "automation_execution_failed", count: 1 }],
    });
    listAIExecutions.mockResolvedValue({ items: [{
      id: "a22217a4-f3a9-4a55-8d41-810ad80a32a0", kind: "reply_draft", status: "succeeded",
      safe_summary: "Reply draft generated", created_at: "2026-10-31T10:00:00Z",
    }], total: 1, limit: 100, offset: 0 });
    submitEvaluation.mockResolvedValue({});
  });

  it("shows real usage data and submits teammate feedback for a completed draft", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><AnalyticsDashboard/></QueryClientProvider>);

    expect(await screen.findByText("32")).toBeInTheDocument();
    expect(screen.getByText("Not configured")).toBeInTheDocument();
    expect(await screen.findByText("Automation run health")).toBeInTheDocument();
    expect(await screen.findByText("Channel delivery health")).toBeInTheDocument();
    expect(screen.getByText("example_chat")).toBeInTheDocument();
    expect(screen.getByText("provider_timeout")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Daily workflow runs grouped by outcome" })).toBeInTheDocument();
    expect(screen.getByText("2026-10-31: 8 runs, 5 succeeded, 1 failed, 2 other.")).toBeInTheDocument();
    expect(screen.getByText("automation_execution_failed")).toBeInTheDocument();
    expect(screen.getByText("42 ms")).toBeInTheDocument();
    const startDate = screen.getByLabelText("Analytics start date") as HTMLInputElement;
    const endDate = screen.getByLabelText("Analytics end date") as HTMLInputElement;
    await waitFor(() => expect(getAutomationMetrics).toHaveBeenCalledWith(30, startDate.value, endDate.value));
    fireEvent.change(startDate, { target: { value: "2026-10-10" } });
    await waitFor(() => expect(getAutomationMetrics).toHaveBeenCalledWith(30, "2026-10-10", endDate.value));
    fireEvent.change(await screen.findByLabelText("Completed draft to evaluate"), {
      target: { value: "a22217a4-f3a9-4a55-8d41-810ad80a32a0" },
    });
    fireEvent.change(screen.getByLabelText("Evaluation category"), { target: { value: "grounding" } });
    fireEvent.click(screen.getByRole("button", { name: "Save evaluation" }));

    await waitFor(() => expect(submitEvaluation).toHaveBeenCalledWith({
      execution_id: "a22217a4-f3a9-4a55-8d41-810ad80a32a0",
      rating: "helpful",
      category: "grounding",
    }));
    expect(await screen.findByText("Evaluation saved.")).toBeInTheDocument();
  });

  it("shows an honest empty state when no integration deliveries exist", async () => {
    getIntegrationDeliveryAnalytics.mockResolvedValue({
      start_date: "2026-10-02", end_date: "2026-10-31", total: 0, succeeded: 0, failed: 0,
      queued: 0, running: 0, cancelled: 0, average_attempts: null, providers: [], daily: [], top_errors: [],
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><AnalyticsDashboard/></QueryClientProvider>);

    expect(await screen.findByText("No outbound integration deliveries were recorded in this date range.")).toBeInTheDocument();
  });

  it("isolates a delivery analytics failure from other dashboard sections", async () => {
    getIntegrationDeliveryAnalytics.mockRejectedValue(new Error("unavailable"));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><AnalyticsDashboard/></QueryClientProvider>);

    expect(await screen.findByText("Channel delivery metrics could not be loaded. Other analytics remain available.")).toBeInTheDocument();
    expect(screen.getByText("Automation run health")).toBeInTheDocument();
  });
});
