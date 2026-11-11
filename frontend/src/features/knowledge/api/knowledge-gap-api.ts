import { api, jsonBody } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type QuestionPeriod = "7" | "30" | "90" | "all";
export type QuestionView = "all" | "grouped" | "ungrouped";
export type QuestionGroup = components["schemas"]["DashboardGroup"];
export type DashboardQuestion = components["schemas"]["DashboardQuestion"];
export type DashboardCounts = components["schemas"]["DashboardCounts"];
type Dashboard = components["schemas"]["KnowledgeGapDashboard"];
type DurableGroup = components["schemas"]["DurableGroupOut"];
export type AnswerDraft = Omit<components["schemas"]["AtomicFAQPublish"], "knowledge_base_id"> & {
  knowledge_base_id: string;
};

const path = "/knowledge/gaps";
export const questionKeys = {
  dashboard: ["customer-questions"] as const,
  groups: ["knowledge-gap-durable"] as const,
  reviews: ["knowledge-gap-reviews"] as const,
};

export function listCustomerQuestions(filters: {
  period: QuestionPeriod;
  view: QuestionView;
  search: string;
  offset: number;
}, signal: AbortSignal) {
  const params = new URLSearchParams({ ...filters, offset: String(filters.offset) });
  return api<Dashboard>(`${path}/dashboard?${params}`, { signal });
}

export const listQuestionGroups = () => api<DurableGroup[]>(`${path}/durable-groups?limit=100`);
export const listQuestionReviews = () => api<components["schemas"]["FAQReviewOut"][]>(`${path}/reviews?limit=100`);

export const questionActions = {
  assign: (threshold: number) => api<{ assigned: number; created: number }>(
    `${path}/durable-groups/auto-assign`, { method: "POST", body: jsonBody({ limit: 100, threshold }) },
  ),
  move: (groupId: string, gapIds: string[]) => api<{ moved: number }>(
    `${path}/durable-groups/${groupId}/members`, { method: "POST", body: jsonBody({ gap_ids: gapIds }) },
  ),
  createGroup: (gapIds: string[]) => api<DurableGroup>(
    `${path}/durable-groups`, { method: "POST", body: jsonBody({ gap_ids: gapIds }) },
  ),
  deleteGroup: (groupId: string) => api<void>(`${path}/durable-groups/${groupId}`, { method: "DELETE" }),
  review: (gapIds: string[], status: "resolved" | "dismissed") => api<{ updated: number }>(
    `${path}/groups/review`, { method: "POST", body: jsonBody({ gap_ids: gapIds, status }) },
  ),
  publish: (draft: AnswerDraft) => api<components["schemas"]["AtomicFAQResult"]>(
    `${path}/groups/publish`, { method: "POST", body: jsonBody(draft) },
  ),
};
