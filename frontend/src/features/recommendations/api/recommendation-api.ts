import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type RecommendationSettings = components["schemas"]["RecommendationSettingsOut"];
export type RecommendationSettingsInput = components["schemas"]["RecommendationSettingsIn"];
export type RecommendationAnalytics = components["schemas"]["RecommendationAnalyticsOut"];

export const recommendationQueryKeys = {
  settings: ["recommendations", "settings"] as const,
  analytics: (start: string, end: string) => ["analytics", "recommendations", start, end] as const,
};

export const getRecommendationSettings = () => api<RecommendationSettings>("/recommendation-settings");
export const updateRecommendationSettings = (input: RecommendationSettingsInput) => api<RecommendationSettings>("/recommendation-settings", { method: "PUT", body: JSON.stringify(input) });
export const getRecommendationAnalytics = (start: string, end: string) => api<RecommendationAnalytics>(`/analytics/recommendations?start_date=${start}&end_date=${end}`);
