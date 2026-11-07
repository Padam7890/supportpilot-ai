import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type ConversationAttachment = components["schemas"]["ConversationAttachmentOut"];

export const conversationAttachmentsKey = (organizationId: string | undefined, conversationId: string | undefined) =>
  ["conversation-attachments", organizationId ?? "unresolved", conversationId ?? "unselected"] as const;

export function listConversationAttachments(conversationId: string) {
  return api<ConversationAttachment[]>(`/conversations/${encodeURIComponent(conversationId)}/attachments`);
}

export async function uploadConversationAttachment(conversationId: string, file: File) {
  const params = new URLSearchParams({ name: file.name });
  const extension = file.name.split(".").pop()?.toLocaleLowerCase();
  const mimeByExtension: Record<string, string> = {
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    webp: "image/webp",
    pdf: "application/pdf",
    txt: "text/plain",
    md: "text/markdown",
  };
  const contentType = mimeByExtension[extension ?? ""] || file.type || "application/octet-stream";
  return api<ConversationAttachment>(`/conversations/${encodeURIComponent(conversationId)}/attachments?${params}`, {
    method: "POST",
    headers: { "content-type": contentType },
    body: await file.arrayBuffer(),
  });
}

export function deleteConversationAttachment(attachmentId: string) {
  return api<void>(`/attachments/${encodeURIComponent(attachmentId)}`, { method: "DELETE" });
}

export async function downloadConversationAttachment(attachmentId: string) {
  const response = await fetch(`/api/attachments/${encodeURIComponent(attachmentId)}/download`, {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`File download failed (HTTP ${response.status}).`);
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  let filename = "conversation-attachment";
  if (encodedName) {
    try {
      filename = decodeURIComponent(encodedName);
    } catch {
      filename = "conversation-attachment";
    }
  }
  return { blob: await response.blob(), filename };
}
