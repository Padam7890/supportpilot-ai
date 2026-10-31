import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type AIUsage = components["schemas"]["AIUsageOut"];
export type AIEvaluationSummary = components["schemas"]["AIEvaluationSummaryOut"];
export type AIEvaluationCreate = components["schemas"]["AIEvaluationCreate"];
export type AIEvaluation = components["schemas"]["AIEvaluationOut"];

export const analyticsQueryKeys = {
  usage: (start: string, end: string) => ["analytics", "ai-usage", start, end] as const,
  evaluations: (start: string, end: string) => ["analytics", "evaluations", start, end] as const,
};

export const getAIUsage = (start: string, end: string) =>
  api<AIUsage>(`/analytics/ai-usage?start_date=${start}&end_date=${end}`);

export const getEvaluationSummary = (start: string, end: string) =>
  api<AIEvaluationSummary>(`/analytics/evaluations?start_date=${start}&end_date=${end}`);

export const submitEvaluation = (data: AIEvaluationCreate) =>
  api<AIEvaluation>("/analytics/evaluations", { method: "POST", body: JSON.stringify(data) });
