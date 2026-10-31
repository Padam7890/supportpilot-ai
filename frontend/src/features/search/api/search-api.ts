import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type SearchResponse = components["schemas"]["SearchResponse"];

export const searchWorkspace = (query: string) =>
  api<SearchResponse>(`/search?q=${encodeURIComponent(query)}&limit=5`);
