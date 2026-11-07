import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type SavedReply = components["schemas"]["SavedReplyOut"];
export type SavedReplyInput = components["schemas"]["SavedReplyCreate"];
export type SavedReplyPatch = components["schemas"]["SavedReplyUpdate"];

export const savedRepliesQueryKey = (organizationId: string | undefined) =>
  ["saved-replies", organizationId ?? "unresolved"] as const;

export function listSavedReplies(includeArchived = false) {
  const query = includeArchived ? "?include_archived=true" : "";
  return api<SavedReply[]>(`/saved-replies${query}`);
}

export function createSavedReply(input: SavedReplyInput) {
  return api<SavedReply>("/saved-replies", { method: "POST", body: JSON.stringify(input) });
}

export function updateSavedReply(id: string, input: SavedReplyPatch) {
  return api<SavedReply>(`/saved-replies/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(input) });
}

export function archiveSavedReply(id: string) {
  return api<SavedReply>(`/saved-replies/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function restoreSavedReply(id: string) {
  return updateSavedReply(id, { is_active: true });
}
