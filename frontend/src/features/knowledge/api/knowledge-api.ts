import { api } from "@/lib/api/client";
import type { KnowledgeDocument, KnowledgeDocumentPage, KnowledgeSearchPage } from "../types/knowledge.types";

export const knowledgeKeys = {
  documents: ["knowledge-documents"] as const,
  search: (query: string) => ["knowledge-search", query] as const,
};

export const listKnowledgeDocuments = () => api<KnowledgeDocumentPage>("/knowledge/documents?limit=50");
export const getKnowledgeDocument = (id: string) => api<KnowledgeDocument>(`/knowledge/documents/${encodeURIComponent(id)}`);

export async function uploadKnowledgeDocument(file: File) {
  const query = new URLSearchParams({ name: file.name });
  const extension = file.name.toLowerCase().split(".").at(-1);
  const contentType = file.type || (extension === "pdf" ? "application/pdf" : extension === "md" ? "text/markdown" : "text/plain");
  return api<KnowledgeDocument>(`/knowledge/documents?${query}`, {
    method: "POST",
    body: await file.arrayBuffer(),
    headers: { "content-type": contentType },
  });
}

export const reprocessKnowledgeDocument = (id: string) =>
  api<KnowledgeDocument>(`/knowledge/documents/${encodeURIComponent(id)}/reprocess`, { method: "POST" });

export const deleteKnowledgeDocument = (id: string) =>
  api<void>(`/knowledge/documents/${encodeURIComponent(id)}`, { method: "DELETE" });

export const searchKnowledge = (query: string) => {
  const params = new URLSearchParams({ q: query, limit: "20" });
  return api<KnowledgeSearchPage>(`/knowledge/documents/search?${params}`);
};
