import { api } from "@/lib/api/client";
import type { KnowledgeDocument, KnowledgeDocumentPage, KnowledgeSearchPage, KnowledgeSourcePreview } from "../types/knowledge.types";

export const KNOWLEDGE_DOCUMENT_PAGE_SIZE = 50;
export const KNOWLEDGE_PROCESSING_POLL_INTERVAL_MS = 3000;

export function isKnowledgeDocumentProcessing(document: KnowledgeDocument): boolean {
  return !document.deleted_at && (document.status === "queued" || document.status === "processing");
}

export const knowledgeKeys = {
  documents: ["knowledge-documents"] as const,
  search: (query: string) => ["knowledge-search", query] as const,
};

export const listKnowledgeDocuments = (knowledgeBaseId?: string, offset = 0) => {
  const params = new URLSearchParams({ limit: String(KNOWLEDGE_DOCUMENT_PAGE_SIZE), offset: String(offset) });
  if (knowledgeBaseId) params.set("knowledge_base_id", knowledgeBaseId);
  return api<KnowledgeDocumentPage>(`/knowledge/documents?${params}`);
};
export const getKnowledgeDocument = (id: string) => api<KnowledgeDocument>(`/knowledge/documents/${encodeURIComponent(id)}`);
export const getKnowledgeSourcePreview = (id: string) =>
  api<KnowledgeSourcePreview>(`/knowledge/documents/${encodeURIComponent(id)}/source-preview`);

export function knowledgePdfUrl(id: string, download = false) {
  return `/api/knowledge/documents/${encodeURIComponent(id)}/pdf${download ? "?download=true" : ""}`;
}

export const moveKnowledgeDocument = (id: string, knowledgeBaseId: string) =>
  api<KnowledgeDocument>(`/knowledge/documents/${encodeURIComponent(id)}/knowledge-base`, {
    method: "PUT",
    body: JSON.stringify({ knowledge_base_id: knowledgeBaseId }),
  });

export async function uploadKnowledgeDocument({ file, knowledgeBaseId }: { file: File; knowledgeBaseId?: string }) {
  const query = new URLSearchParams({ name: file.name });
  if (knowledgeBaseId) query.set("knowledge_base_id", knowledgeBaseId);
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

export const searchKnowledge = (query: string, knowledgeBaseId?: string) => {
  const params = new URLSearchParams({ q: query, limit: "20" });
  if (knowledgeBaseId) params.set("knowledge_base_id", knowledgeBaseId);
  return api<KnowledgeSearchPage>(`/knowledge/documents/search?${params}`);
};
