"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Building2, Copy, MailPlus, ShieldCheck, UserRound, Users } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { createInvitation, getOrganization, listInvitations, listMembers, revokeInvitation, updateMember as patchMember, updateOrganization } from "../api/organization-api";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { inviteSchema, organizationSchema } from "../schemas/organization.schema";
import { ShopifyIntegrationCard } from "@/features/integrations/components/shopify-integration-card";
import { StorefrontWidgetCard } from "@/features/integrations/components/storefront-widget-card";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [inviteLink, setInviteLink] = useState("");
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const organization = useQuery({ queryKey: ["organization"], queryFn: getOrganization });
  const members = useQuery({ queryKey: ["users"], queryFn: listMembers });
  const invitations = useQuery({ queryKey: ["invitations"], queryFn: listInvitations });
  const teamForm = useForm<z.infer<typeof inviteSchema>>({ resolver: zodResolver(inviteSchema), defaultValues: { role: "agent" } });
  const orgForm = useForm<z.infer<typeof organizationSchema>>({ resolver: zodResolver(organizationSchema) });
  const currentRole = me.data?.role;
  const canGrantAdmin = currentRole === "owner";
  const invite = useMutation({
    mutationFn: createInvitation,
    onSuccess: async (result) => {
      teamForm.reset({ role: "agent", email: "" });
      setInviteLink(`${window.location.origin}/invite/${result.invite_token}`);
      await queryClient.invalidateQueries({ queryKey: ["invitations"] });
    },
  });
  const updateMember = useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: { role?: string; is_active?: boolean } }) => patchMember(id, changes),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["users"] }); await queryClient.invalidateQueries({ queryKey: ["me"] }); },
  });
  const updateOrg = useMutation({
    mutationFn: updateOrganization,
    onSuccess: async (saved) => { queryClient.setQueryData(["organization"], saved); await queryClient.invalidateQueries({ queryKey: ["me"] }); },
  });
  const revokeInvite = useMutation({
    mutationFn: revokeInvitation,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["invitations"] }),
  });

  return (
    <div className="space-y-6">
      <div><p className="text-sm font-semibold text-blue-700">Workspace preferences</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Settings & team</h1><p className="mt-2 text-sm text-slate-500">Manage your workspace profile and team access.</p></div>
      <section id="integrations" aria-label="Workspace integrations" className="space-y-5"><ShopifyIntegrationCard/><StorefrontWidgetCard/></section>
      <Panel><PanelHeader title="Organization" description="Workspace details shown to your support team." action={<span className="grid size-9 place-items-center rounded-xl bg-blue-50 text-blue-700"><Building2 size={18}/></span>}/><PanelBody><form className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end" onSubmit={orgForm.handleSubmit((values) => updateOrg.mutate(values))}><Field label="Organization name" error={orgForm.formState.errors.name?.message}><Input defaultValue={organization.data?.name} key={organization.data?.name} {...orgForm.register("name")}/></Field><Field label="Organization slug"><Input value={organization.data?.slug ?? ""} disabled readOnly/></Field><Button type="submit" disabled={updateOrg.isPending}>{updateOrg.isPending ? "Saving…" : "Save changes"}</Button></form>{updateOrg.isError && <p role="alert" className="mt-3 text-sm text-red-700">{updateOrg.error instanceof ApiError ? updateOrg.error.message : "Workspace could not be updated."}</p>}{updateOrg.isSuccess && <p role="status" className="mt-3 text-sm text-emerald-700">Workspace updated.</p>}</PanelBody></Panel>
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.8fr)]">
        <Panel><PanelHeader title="Team members" description="Active teammates and workspace roles" action={<span className="grid size-9 place-items-center rounded-xl bg-violet-50 text-violet-700"><Users size={18}/></span>}/><PanelBody>
          {members.isPending ? <div className="h-40 animate-pulse rounded-xl bg-slate-100"/> : members.isError ? <p role="alert" className="text-sm text-red-700">Unable to load team members.</p> : <div className="divide-y divide-slate-100">{members.data?.map((member) => <div key={member.id} className="flex flex-wrap items-center gap-3 py-4 first:pt-0 last:pb-0"><span className="grid size-10 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600"><UserRound size={17}/></span><div className="min-w-36 flex-1"><p className="font-semibold text-slate-900">{member.full_name}{member.id === me.data?.id && <span className="ml-2 text-xs font-normal text-slate-400">You</span>}</p><p className="mt-1 text-xs text-slate-500">{member.email}{!member.is_active && " · deactivated"}</p></div>{member.role === "owner" ? <span className="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-semibold capitalize text-amber-700">Owner</span> : currentRole === "owner" || (currentRole === "admin" && member.role !== "admin") ? <Select className="min-h-9 w-32 px-2 text-xs" aria-label={`Role for ${member.full_name}`} value={member.role} disabled={updateMember.isPending} onChange={(event) => updateMember.mutate({ id: member.id, changes: { role: event.target.value } })}><option value="admin">Admin</option><option value="agent">Agent</option><option value="viewer">Viewer</option></Select> : <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-semibold capitalize text-blue-700">{member.role}</span>}{currentRole && ["owner", "admin"].includes(currentRole) && member.role !== "owner" && <Button variant={member.is_active ? "ghost" : "secondary"} size="sm" disabled={updateMember.isPending} onClick={() => updateMember.mutate({ id: member.id, changes: { is_active: !member.is_active } })}>{member.is_active ? "Deactivate" : "Reactivate"}</Button>}</div>)}</div>}
          {updateMember.isError && <p role="alert" className="mt-4 text-sm text-red-700">{updateMember.error instanceof ApiError ? updateMember.error.message : "Member could not be updated."}</p>}
        </PanelBody></Panel>
        <Panel><PanelHeader title="Invite a teammate" description="Create a one-time link to share directly." action={<span className="grid size-9 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><MailPlus size={18}/></span>}/><PanelBody>
          <form className="space-y-4" onSubmit={teamForm.handleSubmit((values) => invite.mutate(values))}><Field label="Work email" error={teamForm.formState.errors.email?.message}><Input type="email" autoComplete="email" {...teamForm.register("email")}/></Field><Field label="Role"><Select {...teamForm.register("role")}><option value="agent">Agent</option><option value="viewer">Viewer</option>{canGrantAdmin && <option value="admin">Admin</option>}</Select></Field>{invite.isError && <p role="alert" className="text-sm text-red-700">{invite.error instanceof ApiError ? invite.error.message : "Invitation could not be created."}</p>}<Button type="submit" disabled={invite.isPending}>{invite.isPending ? "Creating link…" : "Create invite link"}</Button></form>
          {inviteLink && <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4"><p className="text-sm font-semibold text-emerald-900">Invite ready to share</p><p className="mt-1 break-all text-xs text-emerald-800">{inviteLink}</p><Button variant="secondary" size="sm" className="mt-3" onClick={() => navigator.clipboard.writeText(inviteLink)}><Copy size={14}/> Copy link</Button><p className="mt-2 text-xs text-emerald-800">This link expires in {Math.ceil(Number(process.env.NEXT_PUBLIC_INVITE_HOURS ?? 72))} hours and works once.</p></div>}
          <div className="mt-6 border-t border-slate-100 pt-5"><h3 className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck size={16} className="text-slate-400"/>Pending invitations</h3><div className="mt-3 space-y-2">{invitations.isPending ? <p className="text-sm text-slate-400">Loading…</p> : invitations.data?.filter((row) => !row.accepted_at && !row.revoked_at).map((row) => <div key={row.id} className="flex items-center justify-between gap-2 rounded-xl bg-slate-50 p-3"><div className="min-w-0"><p className="truncate text-sm font-medium">{row.email}</p><p className="text-xs capitalize text-slate-500">{row.role} · expires {formatDate(row.expires_at)}</p></div><Button size="sm" variant="ghost" onClick={() => revokeInvite.mutate(row.id)}>Revoke</Button></div>)}</div></div>
        </PanelBody></Panel>
      </div>
      <p className="text-xs text-slate-500">Admins can invite Agents and Viewers. Only Owners can invite or grant Admin access.</p>
    </div>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>{label}</span>{children}{error && <span className="block text-xs font-normal text-red-600">{error}</span>}</label>;
}
