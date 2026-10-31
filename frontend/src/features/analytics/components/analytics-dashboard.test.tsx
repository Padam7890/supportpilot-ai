import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AnalyticsDashboard } from "./analytics-dashboard";

const { getAIUsage, getEvaluationSummary, submitEvaluation, listAIExecutions } = vi.hoisted(() => ({
  getAIUsage: vi.fn(),
  getEvaluationSummary: vi.fn(),
  submitEvaluation: vi.fn(),
  listAIExecutions: vi.fn(),
}));

vi.mock("../api/analytics-api", () => ({
  analyticsQueryKeys: {
    usage: (start: string, end: string) => ["usage", start, end],
    evaluations: (start: string, end: string) => ["evaluations", start, end],
  },
  getAIUsage,
  getEvaluationSummary,
  submitEvaluation,
}));
vi.mock("@/features/ai/api/ai-api", () => ({ listAIExecutions }));

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
    fireEvent.change(screen.getByLabelText("Completed draft to evaluate"), {
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
});
