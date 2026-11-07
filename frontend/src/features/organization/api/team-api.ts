import { api } from "@/lib/api/client";

export type TeamMember = { id: string; full_name: string; email: string; role: string };
export type SupportTeam = {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  members: TeamMember[];
  active_ticket_count: number;
  created_at: string;
  updated_at: string;
};

export const teamQueryKey = ["support-teams"] as const;
export const listTeams = () => api<SupportTeam[]>("/teams?include_inactive=true");
export const activeTeamsQueryKey = ["support-teams", "active"] as const;
export const listActiveTeams = () => api<SupportTeam[]>("/teams");
export const createTeam = (input: { name: string; description?: string | null; member_ids: string[] }) =>
  api<SupportTeam>("/teams", { method: "POST", body: JSON.stringify(input) });
export const updateTeam = (id: string, input: { name?: string; description?: string | null; is_active?: boolean }) =>
  api<SupportTeam>(`/teams/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(input) });
export const replaceTeamMembers = (id: string, memberIds: string[]) =>
  api<SupportTeam>(`/teams/${encodeURIComponent(id)}/members`, {
    method: "PUT",
    body: JSON.stringify({ member_ids: memberIds }),
  });
