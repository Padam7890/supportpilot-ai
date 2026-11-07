import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type AIExecution = components["schemas"]["AIExecutionOut"];
export type AIExecutionRetry = components["schemas"]["AIExecutionRetryOut"];
export type AIExecutionPage = components["schemas"]["AIExecutionPage"];
export type AIPlaygroundRequest = components["schemas"]["AIPlaygroundRequest"];
export type AIPlaygroundRetrievalPreviewRequest = components["schemas"]["AIPlaygroundRetrievalPreviewRequest"];
export type AIPlaygroundRetrievalPreview = components["schemas"]["AIPlaygroundRetrievalPreviewOut"];
export type AIReplyDraftRequest = components["schemas"]["AIReplyDraftRequest"];
export type WidgetAIReplyStatus = components["schemas"]["WidgetAIReplyStatusOut"];

export const aiQueryKeys = {
  execution: (id: string | undefined) => ["ai-execution", id] as const,
  history: ["ai-executions"] as const,
};

export const createPlaygroundExecution = (values: AIPlaygroundRequest) =>
  api<AIExecution>("/ai/playground", { method: "POST", body: JSON.stringify(values) });

export const previewPlaygroundRetrieval = (values: AIPlaygroundRetrievalPreviewRequest) =>
  api<AIPlaygroundRetrievalPreview>("/ai/playground/retrieval-preview", { method: "POST", body: JSON.stringify(values) });

export const createReplyDraft = (values: AIReplyDraftRequest) =>
  api<AIExecution>("/ai/reply-drafts", { method: "POST", body: JSON.stringify(values) });

export const getAIExecution = (id: string) => api<AIExecution>(`/ai/executions/${id}`);
export const retryAIExecution = (id: string) =>
  api<AIExecutionRetry>(`/ai/executions/${encodeURIComponent(id)}/retry`, { method: "POST" });
export const getWidgetAIReplyStatus = (conversationId: string) =>
  api<WidgetAIReplyStatus | null>(`/ai/conversations/${conversationId}/widget-reply`);

export const listAIExecutions = (limit = 50, offset = 0) =>
  api<AIExecutionPage>(`/ai/executions?limit=${limit}&offset=${offset}`);
