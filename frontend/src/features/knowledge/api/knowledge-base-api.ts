import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type KnowledgeBase = components["schemas"]["KnowledgeBaseOut"];
export type KnowledgeBasePage = components["schemas"]["KnowledgeBasePage"];
export type KnowledgeBaseAuditPage = components["schemas"]["KnowledgeBaseAuditPage"];
export const knowledgeBaseKey = ["knowledge-bases"] as const;

export const listKnowledgeBases = () => api<KnowledgeBasePage>("/knowledge/bases?limit=100");
export const getKnowledgeBase = (id: string) => api<KnowledgeBase>(`/knowledge/bases/${encodeURIComponent(id)}`);
export const createKnowledgeBase = (values: { name: string; description: string | null }) =>
  api<KnowledgeBase>("/knowledge/bases", { method: "POST", body: JSON.stringify(values) });
export const updateKnowledgeBase = (id: string, values: { name: string; description: string | null }) =>
  api<KnowledgeBase>(`/knowledge/bases/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(values) });
export const archiveKnowledgeBase = (id: string) =>
  api<KnowledgeBase>(`/knowledge/bases/${encodeURIComponent(id)}/archive`, { method: "POST" });
export const restoreKnowledgeBase = (id: string) =>
  api<KnowledgeBase>(`/knowledge/bases/${encodeURIComponent(id)}/restore`, { method: "POST" });
export const makeDefaultKnowledgeBase = (id: string) =>
  api<KnowledgeBase>(`/knowledge/bases/${encodeURIComponent(id)}/make-default`, { method: "POST" });
export const listKnowledgeBaseAudit = (id: string, offset = 0) =>
  api<KnowledgeBaseAuditPage>(`/knowledge/bases/${encodeURIComponent(id)}/audit?limit=10&offset=${offset}`);
