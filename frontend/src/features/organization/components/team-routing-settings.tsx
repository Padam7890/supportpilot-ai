"use client";

import { Checkbox } from "@/components/ui";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Users } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { listMembers } from "../api/organization-api";
import { createTeam, listTeams, replaceTeamMembers, teamQueryKey, updateTeam } from "../api/team-api";

export function TeamRoutingSettings() {
  const queryClient = useQueryClient();
  const teams = useQuery({ queryKey: teamQueryKey, queryFn: listTeams });
  const members = useQuery({ queryKey: ["users"], queryFn: listMembers });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [draftMemberIds, setDraftMemberIds] = useState<string[]>([]);
  const refresh = async () => queryClient.invalidateQueries({ queryKey: teamQueryKey });
  const create = useMutation({
    mutationFn: createTeam,
    onSuccess: async (team) => {
      setName("");
      setDescription("");
      setSelectedTeamId(team.id);
      setEditName(team.name);
      setEditDescription(team.description ?? "");
      setDraftMemberIds(team.members.map((member) => member.id));
      await refresh();
    },
  });
  const saveMembers = useMutation({ mutationFn: ({ id, ids }: { id: string; ids: string[] }) => replaceTeamMembers(id, ids), onSuccess: refresh });
  const saveTeam = useMutation({ mutationFn: ({ id, values }: { id: string; values: { name: string; description: string | null } }) => updateTeam(id, values), onSuccess: refresh });
  const toggleTeam = useMutation({ mutationFn: ({ id, active }: { id: string; active: boolean }) => updateTeam(id, { is_active: active }), onSuccess: refresh });

  const selectedTeam = teams.data?.find((team) => team.id === selectedTeamId) ?? null;
  const eligibleMembers = members.data?.filter((member) => member.is_active && ["owner", "admin", "agent"].includes(member.role)) ?? [];

  return <div className="space-y-5">
    <Panel>
      <PanelHeader title="Support teams" description="Group agents and route tickets to the right team. Teams are private to this workspace." action={<span className="grid size-9 place-items-center rounded-xl bg-blue-50 text-blue-700"><Users size={18}/></span>}/>
      <PanelBody className="space-y-5">
        <form className="grid gap-3 md:grid-cols-[1fr_1.4fr_auto] md:items-end" onSubmit={(event) => { event.preventDefault(); create.mutate({ name, description: description || null, member_ids: [] }); }}>
          <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Team name</span><Input value={name} onChange={(event) => setName(event.target.value)} minLength={2} maxLength={120} required placeholder="e.g. Returns"/></label>
          <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Description <span className="font-normal text-slate-400">(optional)</span></span><Input value={description} onChange={(event) => setDescription(event.target.value)} maxLength={1000} placeholder="What this team handles"/></label>
          <Button type="submit" disabled={create.isPending || name.trim().length < 2}><Plus size={16}/>{create.isPending ? "Creating…" : "Create team"}</Button>
        </form>
        {create.isError && <ErrorMessage error={create.error} fallback="Team could not be created."/>}
        {teams.isPending ? <div role="status" className="h-28 animate-pulse rounded-xl bg-slate-100"/> : teams.isError ? <div><ErrorMessage error={teams.error} fallback="Teams could not be loaded."/><Button className="mt-3" variant="secondary" onClick={() => void teams.refetch()}>Try again</Button></div> : teams.data?.length ? <div className="divide-y divide-slate-100 rounded-xl border border-slate-200">
          {teams.data.map((team) => <div key={team.id} className="flex flex-wrap items-center gap-3 p-4">
            <Button variant="unstyled" type="button" aria-pressed={selectedTeamId === team.id} onClick={() => { setSelectedTeamId(team.id); setEditName(team.name); setEditDescription(team.description ?? ""); setDraftMemberIds(team.members.map((member) => member.id)); }} className={`min-w-0 flex-1 rounded-lg px-2 py-1 text-left ${selectedTeamId === team.id ? "bg-blue-50" : "hover:bg-slate-50"}`}>
              <span className="flex items-center gap-2 font-semibold text-slate-900">{team.name}{!team.is_active && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-500">Inactive</span>}</span>
              <span className="mt-1 block text-xs text-slate-500">{team.members.length} members · {team.active_ticket_count} open tickets{team.description ? ` · ${team.description}` : ""}</span>
            </Button>
            <Button type="button" size="sm" variant="secondary" disabled={toggleTeam.isPending} onClick={() => toggleTeam.mutate({ id: team.id, active: !team.is_active })}>{team.is_active ? "Deactivate" : "Activate"}</Button>
          </div>)}
        </div> : <div className="rounded-xl border border-dashed border-slate-300 px-5 py-8 text-center"><Users className="mx-auto text-slate-400" size={24}/><p className="mt-2 font-medium text-slate-800">No teams yet</p><p className="mt-1 text-sm text-slate-500">Create a team to organize incoming support tickets.</p></div>}
        {toggleTeam.isError && <ErrorMessage error={toggleTeam.error} fallback="Team status could not be changed."/>}
      </PanelBody>
    </Panel>

    {selectedTeam && <Panel>
      <PanelHeader title="Team details" description="Keep the team name and routing purpose clear."/>
      <PanelBody>
        <form className="grid gap-3 md:grid-cols-[1fr_1.5fr_auto] md:items-end" onSubmit={(event) => { event.preventDefault(); saveTeam.mutate({ id: selectedTeam.id, values: { name: editName, description: editDescription || null } }); }}>
          <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Name</span><Input value={editName} onChange={(event) => setEditName(event.target.value)} minLength={2} maxLength={120} required disabled={!selectedTeam.is_active}/></label>
          <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>Description</span><Input value={editDescription} onChange={(event) => setEditDescription(event.target.value)} maxLength={1000} disabled={!selectedTeam.is_active}/></label>
          <Button type="submit" disabled={!selectedTeam.is_active || saveTeam.isPending || (editName.trim() === selectedTeam.name && (editDescription || "") === (selectedTeam.description ?? ""))}>{saveTeam.isPending ? "Saving…" : "Save details"}</Button>
        </form>
        {saveTeam.isError && <div className="mt-3"><ErrorMessage error={saveTeam.error} fallback="Team details could not be updated."/></div>}
        {saveTeam.isSuccess && <p role="status" className="mt-3 text-sm text-emerald-700">Team details updated.</p>}
      </PanelBody>
    </Panel>}

    {selectedTeam && <Panel>
      <PanelHeader title={`${selectedTeam.name} members`} description="Only active Owners, Admins, and Agents can be added to a team."/>
      <PanelBody>
        {members.isPending ? <p role="status" className="text-sm text-slate-500">Loading workspace members…</p> : members.isError ? <ErrorMessage error={members.error} fallback="Workspace members could not be loaded."/> : eligibleMembers.length ? <>
          <div className="grid gap-2 sm:grid-cols-2">{eligibleMembers.map((member) => <label key={member.id} className="flex min-h-12 items-center gap-3 rounded-xl border border-slate-200 px-3 py-2.5 text-sm hover:bg-slate-50"><Checkbox className="size-4 rounded border-slate-300 text-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600" checked={draftMemberIds.includes(member.id)} disabled={!selectedTeam.is_active || saveMembers.isPending} onCheckedChange={(checked) => setDraftMemberIds((current) => checked === true ? [...current, member.id] : current.filter((id) => id !== member.id))}/><span className="min-w-0 flex-1"><span className="block truncate font-medium text-slate-800">{member.full_name}</span><span className="block truncate text-xs text-slate-500">{member.email} · {member.role}</span></span></label>)}</div>
          <div className="mt-4 flex flex-wrap items-center gap-3"><Button type="button" disabled={!selectedTeam.is_active || saveMembers.isPending || sameIds(draftMemberIds, selectedTeam.members.map((member) => member.id))} onClick={() => saveMembers.mutate({ id: selectedTeam.id, ids: draftMemberIds })}>{saveMembers.isPending ? "Saving…" : "Save team members"}</Button>{!selectedTeam.is_active && <span className="text-xs text-slate-500">Activate this team before editing members.</span>}</div>
          {saveMembers.isError && <ErrorMessage error={saveMembers.error} fallback="Team members could not be updated."/>}
          {saveMembers.isSuccess && <p role="status" className="mt-3 text-sm text-emerald-700">Team members updated.</p>}
        </> : <p className="text-sm text-slate-500">No eligible active members are available to add.</p>}
      </PanelBody>
    </Panel>}
    <p className="text-xs leading-5 text-slate-500">Ticket routing is available to Owners and Admins. Agents can claim tickets routed to teams they belong to.</p>
  </div>;
}

function sameIds(left: string[], right: string[]) {
  return left.length === right.length && left.every((id) => right.includes(id));
}

function ErrorMessage({ error, fallback }: { error: unknown; fallback: string }) {
  return <p role="alert" className="text-sm text-red-700">{error instanceof ApiError ? error.message : fallback}</p>;
}
