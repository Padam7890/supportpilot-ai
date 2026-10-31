import { api } from "@/lib/api/client";
import type { User } from "../types/user.types";
import type { InviteAcceptanceValues, LoginValues, RegisterValues } from "../schemas/auth.schema";

export type InvitationPreview = { email: string; organization_name: string; role: string };

export const currentUserQueryKey = ["me"] as const;
export const getCurrentUser = () => api<User>("/auth/me");
export const logout = () => api<void>("/auth/logout", { method: "POST" });

export function login(values: LoginValues) {
  return api<void>("/auth/login", { method: "POST", body: JSON.stringify(values) });
}

export function register(values: RegisterValues) {
  return api<void>("/auth/register", { method: "POST", body: JSON.stringify(values) });
}

export function previewInvitation(token: string) {
  return api<InvitationPreview>(`/auth/invitations/${encodeURIComponent(token)}`);
}

export function acceptInvitation(token: string, values: InviteAcceptanceValues) {
  return api<void>("/auth/invitations/accept", {
    method: "POST",
    body: JSON.stringify({ ...values, invite_token: token }),
  });
}
