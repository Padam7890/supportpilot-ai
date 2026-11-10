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
export type WorkspaceChoice = {
  membership_id: string;
  organization_name: string;
  organization_slug: string;
};
export type LoginStart =
  | { status: "workspace_selection_required"; workspaces: WorkspaceChoice[]; email_hint?: string }
  | { status: "otp_required"; workspaces: []; email_hint?: string }
  | { user: User };
type AuthFlowMessage = { status: string; message: string; email_hint?: string };
export type AuthFlowStatus = AuthFlowMessage | { user: User };
export type AuthSessionPage = components["schemas"]["SessionPage"];

export const currentUserQueryKey = ["me"] as const;
export const getCurrentUser = () => api<User>("/auth/me");
export const logout = () => api<void>("/auth/logout", { method: "POST" });
export const listAuthSessions = (offset = 0) =>
  api<AuthSessionPage>(`/auth/sessions?limit=25&offset=${offset}`);
export const revokeAuthSession = (sessionId: string) =>
  api<void>(`/auth/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });

export function login(values: LoginValues) {
  return api<LoginStart>("/auth/login", { method: "POST", body: JSON.stringify(values) });
}

export function selectLoginWorkspace(membership_id: string) {
  return api<AuthFlowStatus>("/auth/login/select-workspace", {
    method: "POST", body: JSON.stringify({ membership_id }),
  });
}

export function verifyLoginCode(code: string) {
  return api<{ user: User }>("/auth/login/verify-code", { method: "POST", body: JSON.stringify({ code }) });
}

export function resendAuthCode() {
  return api<AuthFlowMessage>("/auth/resend-code", { method: "POST", body: JSON.stringify({}) });
}

export function register(values: RegisterValues) {
  return api<{ status: "email_verification_required"; organization_name: string; organization_slug: string }>(
    "/auth/register", { method: "POST", body: JSON.stringify(values) },
  );
}

export function verifyRegistrationCode(code: string) {
  return api<RegistrationPending>("/auth/register/verify-email", {
    method: "POST", body: JSON.stringify({ code }),
  });
}

export function requestPasswordReset(email: string) {
  return api<AuthFlowMessage>("/auth/password-reset/request", {
    method: "POST", body: JSON.stringify({ email }),
  });
}

export function completePasswordReset(code: string, new_password: string) {
  return api<AuthFlowStatus>("/auth/password-reset/complete", {
    method: "POST", body: JSON.stringify({ code, new_password }),
  });
}

export function previewInvitation(token: string) {
  return api<InvitationPreview>(`/auth/invitations/${encodeURIComponent(token)}`);
}

export function acceptInvitation(token: string, values: InviteAcceptanceValues) {
  return api<AuthFlowStatus>("/auth/invitations/accept", {
    method: "POST",
    body: JSON.stringify({ ...values, invite_token: token }),
  });
}
