import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";
import type { User } from "../types/user.types";
import type { InviteAcceptanceValues, LoginValues, RegisterValues } from "../schemas/auth.schema";

export type InvitationPreview = { email: string; organization_name: string; role: string };
export type RegistrationPending = {
  status: "pending_approval";
  organization_name: string;
  organization_slug: string;
};
export type AuthSessionPage = components["schemas"]["SessionPage"];

export const currentUserQueryKey = ["me"] as const;
export const getCurrentUser = () => api<User>("/auth/me");
export const logout = () => api<void>("/auth/logout", { method: "POST" });
export const listAuthSessions = (offset = 0) =>
  api<AuthSessionPage>(`/auth/sessions?limit=25&offset=${offset}`);
export const revokeAuthSession = (sessionId: string) =>
  api<void>(`/auth/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });

export function login(values: LoginValues) {
  return api<void>("/auth/login", { method: "POST", body: JSON.stringify(values) });
}

export function register(values: RegisterValues) {
  return api<RegistrationPending>("/auth/register", { method: "POST", body: JSON.stringify(values) });
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
