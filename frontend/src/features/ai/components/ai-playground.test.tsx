import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AIPlayground } from "./ai-playground";

const { createPlaygroundExecution, getAIExecution, getCurrentUser, listAIAgents } = vi.hoisted(() => ({
  createPlaygroundExecution: vi.fn(),
  getAIExecution: vi.fn(),
  getCurrentUser: vi.fn(),
  listAIAgents: vi.fn(),
}));

vi.mock("../api/ai-api", () => ({
  aiQueryKeys: { execution: (id: string | undefined) => ["ai-execution", id], history: ["ai-executions"] },
  createPlaygroundExecution,
  getAIExecution,
}));

vi.mock("@/features/auth/api/auth-api", () => ({ getCurrentUser }));
vi.mock("../api/ai-agent-api", () => ({ aiAgentsKey: ["ai-agents"], listAIAgents }));

const succeededExecution = {
  id: "a22217a4-f3a9-4a55-8d41-810ad80a32a0",
  ai_agent_id: "9aa5f49c-c5b4-4e55-b34c-67a9cff31610",
  ai_agent_config_version: 2,
  kind: "playground" as const,
  status: "succeeded" as const,
  safe_summary: "Playground answer generated using 1 knowledge source(s).",
  draft: "Unused products may be returned within thirty days.",
  citations: [{ document_id: "a6b6b3aa-2337-494d-9cf6-fd82e15fb35c", document_name: "returns.txt", chunk_index: 0, excerpt: "Unused products can be returned within thirty days." }],
  tool_outcomes: [{ tool: "tenant_knowledge_search", status: "completed", result_count: 1 }],
  usage: { prompt_tokens: 20, completion_tokens: 12, total_tokens: 32 },
  model_name: "test-model",
  error_code: null,
  created_at: "2026-10-31T10:00:00Z",
  updated_at: "2026-10-31T10:00:01Z",
  started_at: "2026-10-31T10:00:00Z",
  completed_at: "2026-10-31T10:00:01Z",
};

function renderPlayground() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><AIPlayground/></QueryClientProvider>);
}

describe("AI playground", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    getCurrentUser.mockResolvedValue({ role: "agent" });
    listAIAgents.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    createPlaygroundExecution.mockResolvedValue({ ...succeededExecution, status: "queued", draft: null, citations: [], completed_at: null });
    getAIExecution.mockResolvedValue(succeededExecution);
  });

  it("polls for a grounded answer and shows its citation without sending a message", async () => {
    const view = renderPlayground();
    const question = screen.getByLabelText("Question");
    fireEvent.change(question, { target: { value: "What is the return policy?" } });
    const submit = view.getByRole("button", { name: "Generate answer" });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);

    expect(await screen.findByText(succeededExecution.draft)).toBeInTheDocument();
    expect(screen.getByText(/bot configuration v2/)).toBeInTheDocument();
    expect(screen.getByText("returns.txt · section 1")).toBeInTheDocument();
    expect(createPlaygroundExecution.mock.calls[0][0]).toEqual({ question: "What is the return policy?" });
    expect(getAIExecution).toHaveBeenCalledWith(succeededExecution.id);
    expect(screen.queryByText(/private reasoning/i)).not.toBeInTheDocument();
  });

  it("keeps generation disabled for viewers", async () => {
    getCurrentUser.mockResolvedValue({ role: "viewer" });
    const view = renderPlayground();
    expect(await view.findByRole("button", { name: "Generate answer" })).toBeDisabled();
  });
});
