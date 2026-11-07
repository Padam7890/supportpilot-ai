import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type AIUsage = components["schemas"]["AIUsageOut"];
export type AIEvaluationSummary = components["schemas"]["AIEvaluationSummaryOut"];
export type AIEvaluationCreate = components["schemas"]["AIEvaluationCreate"];
export type AIEvaluation = components["schemas"]["AIEvaluationOut"];
export type IntegrationDeliveryAnalytics = components["schemas"]["IntegrationDeliveryAnalyticsOut"];
export type CommerceApprovalAnalytics = components["schemas"]["CommerceApprovalAnalyticsOut"];
export type SupportResponseAnalytics = components["schemas"]["SupportResponseAnalyticsOut"];
export type OperationalAlerts = components["schemas"]["OperationalAlertsOut"];
export type FailedBackgroundJobs = components["schemas"]["FailedBackgroundJobsOut"];

export const analyticsQueryKeys = {
  usage: (start: string, end: string) => ["analytics", "ai-usage", start, end] as const,
  evaluations: (start: string, end: string) => ["analytics", "evaluations", start, end] as const,
  integrationDeliveries: (start: string, end: string) => ["analytics", "integration-deliveries", start, end] as const,
  commerceApprovals: (start: string, end: string) => ["analytics", "commerce-approvals", start, end] as const,
  supportResponses: (start: string, end: string) => ["analytics", "support-response-times", start, end] as const,
  operationalAlerts: () => ["analytics", "operational-alerts"] as const,
};

export const getAIUsage = (start: string, end: string) =>
  api<AIUsage>(`/analytics/ai-usage?start_date=${start}&end_date=${end}`);

export const getEvaluationSummary = (start: string, end: string) =>
  api<AIEvaluationSummary>(`/analytics/evaluations?start_date=${start}&end_date=${end}`);

export const getIntegrationDeliveryAnalytics = (start: string, end: string) =>
  api<IntegrationDeliveryAnalytics>(`/analytics/integration-deliveries?start_date=${start}&end_date=${end}`);

export const getCommerceApprovalAnalytics = (start: string, end: string) =>
  api<CommerceApprovalAnalytics>(`/analytics/commerce-approvals?start_date=${start}&end_date=${end}`);

export const getSupportResponseAnalytics = (start: string, end: string) =>
  api<SupportResponseAnalytics>(`/analytics/support-response-times?start_date=${start}&end_date=${end}`);

export const getOperationalAlerts = () => api<OperationalAlerts>("/analytics/operational-alerts");
export const getFailedBackgroundJobs = (limit = 20) =>
  api<FailedBackgroundJobs>(`/analytics/background-failures?limit=${limit}`);

export const submitEvaluation = (data: AIEvaluationCreate) =>
  api<AIEvaluation>("/analytics/evaluations", { method: "POST", body: JSON.stringify(data) });
