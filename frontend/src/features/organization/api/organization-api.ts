import { api } from "@/lib/api/client";
import type { User } from "@/features/auth/types/user.types";
import type { Invitation } from "../types/invitation.types";
import type { InviteValues, OrganizationValues } from "../schemas/organization.schema";

export type Organization = { id: string; name: string; slug: string };

export const organizationQueryKeys = {
  organization: ["organization"] as const,
  members: ["users"] as const,
  invitations: ["invitations"] as const,
};

export const getOrganization = () => api<Organization>("/organization");
export const updateOrganization = (values: OrganizationValues) =>
  api<Organization>("/organization", { method: "PATCH", body: JSON.stringify(values) });
export const listMembers = () => api<User[]>("/users");
export const updateMember = (id: string, changes: { role?: string; is_active?: boolean }) =>
  api<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(changes) });
export const listInvitations = () => api<Invitation[]>("/users/invitations");
export const createInvitation = (values: InviteValues) =>
  api<Invitation>("/users/invitations", { method: "POST", body: JSON.stringify(values) });
export const revokeInvitation = (id: string) => api(`/users/invitations/${id}`, { method: "DELETE" });
