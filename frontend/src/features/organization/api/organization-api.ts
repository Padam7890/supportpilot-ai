import { api } from "@/lib/api/client";
import type { User } from "@/features/auth/types/user.types";
import type { Invitation } from "../types/invitation.types";
import type { InviteValues, OrganizationValues } from "../schemas/organization.schema";
import type { components } from "@/lib/api/generated";

export type Organization = { id: string; name: string; slug: string };
export type FirstResponseSlaPolicy = { low: number; normal: number; high: number; urgent: number };
export type WorkspaceAuditPage = components["schemas"]["WorkspaceAuditPage"];

export const organizationQueryKeys = {
  organization: ["organization"] as const,
  members: ["users"] as const,
  invitations: ["invitations"] as const,
};

export const getOrganization = () => api<Organization>("/organization");
export const updateOrganization = (values: OrganizationValues) =>
  api<Organization>("/organization", { method: "PATCH", body: JSON.stringify(values) });
export const getFirstResponseSla = () => api<FirstResponseSlaPolicy>("/organization/sla");
export const updateFirstResponseSla = (values: FirstResponseSlaPolicy) =>
  api<FirstResponseSlaPolicy>("/organization/sla", { method: "PUT", body: JSON.stringify(values) });
export const getWorkspaceAudit = (offset = 0) =>
  api<WorkspaceAuditPage>(`/organization/audit?limit=50&offset=${offset}`);
export const listMembers = () => api<User[]>("/users");
export const updateMember = (id: string, changes: { role?: string; is_active?: boolean }) =>
  api<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(changes) });
export const listInvitations = () => api<Invitation[]>("/users/invitations");
export const createInvitation = (values: InviteValues) =>
  api<Invitation>("/users/invitations", { method: "POST", body: JSON.stringify(values) });
export const revokeInvitation = (id: string) => api(`/users/invitations/${id}`, { method: "DELETE" });
