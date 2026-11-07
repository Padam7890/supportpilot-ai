"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Bot, BookOpen, Building2, Clock3, Copy, MailPlus, MessageCircle, PenLine, Plug, Search, Settings2, ShieldCheck, Sparkles, Type, UserRound, Users, Workflow } from "lucide-react";
import { TypographyScalePicker } from "./typography-scale-picker";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { createInvitation, getOrganization, listInvitations, listMembers, revokeInvitation, updateMember as patchMember, updateOrganization } from "../api/organization-api";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { inviteSchema, organizationSchema } from "../schemas/organization.schema";
import { ShopifyIntegrationCard } from "@/features/integrations/components/shopify-integration-card";
import { ProviderOverview } from "@/features/integrations/components/provider-overview";
import { StorefrontWidgetCard } from "@/features/integrations/components/storefront-widget-card";
import { RecommendationSettingsCard } from "@/features/recommendations/components/recommendation-settings-card";
import { SecuritySessions } from "@/features/auth/components/security-sessions";
import { TeamRoutingSettings } from "./team-routing-settings";
import { FirstResponseSlaSettings } from "./first-response-sla-settings";
import { SavedRepliesSettings } from "./saved-replies-settings";
import { settingsSectionFromHash, settingsSectionHash, type SettingsSection } from "../utils/settings-section";

type SettingsNavigationItem = { id?: SettingsSection; href?: string; label: string; icon: typeof Building2 };

const settingsGroups: { label: string; items: SettingsNavigationItem[] }[] = [
  { label: "Workspace", items: [{ id: "general", label: "General", icon: Building2 }, { id: "appearance", label: "Appearance", icon: Type }, { id: "team", label: "Team & roles", icon: Users }, { id: "sla", label: "Inbox & SLAs", icon: Clock3 }, { id: "saved-replies", label: "Saved replies", icon: PenLine }, { id: "security", label: "Security", icon: ShieldCheck }] },
  { label: "AI & automation", items: [{ href: "/dashboard/ai/agents", label: "AI Bots", icon: Bot }, { href: "/dashboard/automations", label: "Automations", icon: Workflow }, { id: "recommendations", label: "Recommendations", icon: Sparkles }, { href: "/dashboard/knowledge", label: "Knowledge Library", icon: BookOpen }, { href: "/dashboard/ai", label: "AI Playground", icon: Sparkles }] },
  { label: "Channels", items: [{ id: "widget", label: "Chat widget", icon: MessageCircle }, { id: "shopify", label: "Integrations", icon: Plug }] },
];

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const pathname = usePathname();
  const [inviteLink, setInviteLink] = useState("");
  const [activeSection, setActiveSection] = useState<SettingsSection>("general");
  const [settingsSearch, setSettingsSearch] = useState("");
  useEffect(() => {
    const syncSectionFromLocation = () => {
      const section = settingsSectionFromHash(window.location.hash);
      if (section) setActiveSection(section);
    };
    syncSectionFromLocation();
    window.addEventListener("popstate", syncSectionFromLocation);
    window.addEventListener("hashchange", syncSectionFromLocation);
    return () => {
      window.removeEventListener("popstate", syncSectionFromLocation);
      window.removeEventListener("hashchange", syncSectionFromLocation);
    };
  }, []);
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const currentRole = me.data?.role;
  const canManageSettings = currentRole === "owner" || currentRole === "admin";
  const visibleSection: SettingsSection = canManageSettings
    ? activeSection
    : activeSection === "appearance"
      ? "appearance"
      : "security";
  const organization = useQuery({ queryKey: ["organization"], queryFn: getOrganization, enabled: canManageSettings });
  const members = useQuery({ queryKey: ["users"], queryFn: listMembers, enabled: canManageSettings && visibleSection === "team" });
  const invitations = useQuery({ queryKey: ["invitations"], queryFn: listInvitations, enabled: canManageSettings && visibleSection === "team" });
  const teamForm = useForm<z.infer<typeof inviteSchema>>({ resolver: zodResolver(inviteSchema), defaultValues: { role: "agent" } });
  const orgForm = useForm<z.infer<typeof organizationSchema>>({ resolver: zodResolver(organizationSchema) });
  const availableGroups = canManageSettings
    ? settingsGroups
    : [{ label: "Account", items: settingsGroups[0].items.filter((item) => item.id === "security" || item.id === "appearance") }];
  const searchTerm = settingsSearch.trim().toLocaleLowerCase();
  const visibleGroups = availableGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        !searchTerm || `${group.label} ${item.label}`.toLocaleLowerCase().includes(searchTerm),
      ),
    }))
    .filter((group) => group.items.length > 0);
  function selectSection(section: SettingsSection) {
    window.history.pushState(null, "", settingsSectionHash(section));
    setActiveSection(section);
  }
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
    <div className="space-y-5">
      <header>
        <p className="text-[13px] font-semibold text-[var(--text-accent)]">Workspace preferences</p>
        <h1 className="page-title mt-1">Settings</h1>
        <p className="page-subtitle mt-2">{canManageSettings ? "Manage your workspace, team, AI recommendations, and connected channels." : "Manage appearance, security, and active sign-in sessions."}</p>
      </header>
      <section aria-label="Settings" className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex min-h-[680px] flex-col md:flex-row">
          <aside aria-label="Settings sections" className="border-b border-slate-200 bg-slate-50/70 p-3 md:w-64 md:shrink-0 md:border-b-0 md:border-r md:p-5">
            <div className="mb-4 hidden items-center gap-3 border-b border-slate-200 px-2 pb-5 md:flex"><span className="grid size-9 place-items-center rounded-xl bg-blue-50 text-blue-700"><Settings2 size={19}/></span><span className="text-lg font-semibold">Settings</span></div>
            <label className="relative mb-4 block">
              <Search size={15} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/>
              <input
                type="search"
                aria-label="Search settings"
                value={settingsSearch}
                onChange={(event) => setSettingsSearch(event.target.value)}
                placeholder="Search settings"
                className="min-h-10 w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30"
              />
            </label>
            <nav className="flex gap-2 overflow-x-auto md:block md:space-y-6" aria-label="Settings navigation">
              {visibleGroups.map((group) => <div key={group.label} className="shrink-0 md:space-y-2"><p className="mb-2 hidden px-3 text-[11px] font-bold uppercase tracking-[.12em] text-slate-600 md:block">{group.label}</p><div className="flex gap-1.5 md:block md:space-y-1">{group.items.map((item) => {
                const Icon = item.icon;
                const sectionId = item.id;
                const selected = item.id ? item.id === visibleSection : Boolean(item.href && (pathname === item.href || pathname.startsWith(`${item.href}/`)));
                const sharedClass = `flex min-h-10 items-center gap-3 whitespace-nowrap rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${selected ? "bg-slate-200 text-slate-950" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"}`;
                if (item.href) return <Link key={item.href} href={item.href} aria-current={selected ? "page" : undefined} className={`${sharedClass} w-full`}><Icon size={17}/><span>{item.label}</span></Link>;
                if (!sectionId) return null;
                return <button key={sectionId} type="button" aria-current={selected ? "page" : undefined} aria-controls="settings-content" onClick={() => selectSection(sectionId)} className={`${sharedClass} w-full text-left`}><Icon size={17}/><span>{item.label}</span></button>;
              })}</div></div>)}
            </nav>
            {visibleGroups.length === 0 && <p role="status" className="px-3 py-2 text-sm text-slate-500">No implemented settings match “{settingsSearch}”.</p>}
          </aside>
          <main id="settings-content" className="min-w-0 flex-1 p-4 sm:p-7 lg:p-9" aria-live="polite">
            <div className="mb-7 border-b border-slate-200 pb-5"><h2 className="section-title">{sectionTitle(visibleSection)}</h2><p className="page-subtitle mt-1.5">{sectionDescription(visibleSection)}</p></div>
            {visibleSection === "appearance" && (
              <Panel>
                <PanelHeader
                  title="Typography"
                  description="Choose how dense type and spacing feel in your dashboard."
                  action={<span className="grid size-9 place-items-center rounded-xl bg-blue-50 text-blue-700"><Type size={18}/></span>}
                />
                <PanelBody>
                  <TypographyScalePicker />
                </PanelBody>
              </Panel>
            )}
            {visibleSection === "general" && <Panel><PanelHeader title="Workspace details" description="Basic information visible to your team." action={<span className="grid size-9 place-items-center rounded-xl bg-blue-50 text-blue-700"><Building2 size={18}/></span>}/><PanelBody><form className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end" onSubmit={orgForm.handleSubmit((values) => updateOrg.mutate(values))}><Field label="Workspace name" error={orgForm.formState.errors.name?.message}><Input defaultValue={organization.data?.name} key={organization.data?.name} {...orgForm.register("name")}/></Field><Field label="Workspace slug"><Input value={organization.data?.slug ?? ""} disabled readOnly/></Field><Button type="submit" disabled={updateOrg.isPending}>{updateOrg.isPending ? "Saving…" : "Save changes"}</Button></form>{updateOrg.isError && <p role="alert" className="mt-3 text-sm text-red-700">{updateOrg.error instanceof ApiError ? updateOrg.error.message : "Workspace could not be updated."}</p>}{updateOrg.isSuccess && <p role="status" className="mt-3 text-sm text-emerald-700">Workspace updated.</p>}</PanelBody></Panel>}
            {visibleSection === "security" && <SecuritySessions/>}
            {visibleSection === "sla" && <FirstResponseSlaSettings/>}
            {visibleSection === "saved-replies" && canManageSettings && <SavedRepliesSettings organizationId={me.data?.organization_id}/>}
            {visibleSection === "team" && <div className="space-y-5">
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
      <TeamRoutingSettings/>
            </div>}
            {visibleSection === "recommendations" && <RecommendationSettingsCard/>}
            {visibleSection === "widget" && <section aria-label="Storefront chat widget"><StorefrontWidgetCard/></section>}
            {visibleSection === "shopify" && <section aria-label="Integrations" className="space-y-5"><ProviderOverview/><ShopifyIntegrationCard/></section>}
          </main>
        </div>
      </section>
    </div>
  );
}

function sectionTitle(section: SettingsSection) {
  return { general: "General", appearance: "Appearance", team: "Team & roles", sla: "Inbox & SLAs", "saved-replies": "Saved replies", security: "Security", recommendations: "Recommendations", widget: "Chat widget", shopify: "Integrations" }[section];
}

function sectionDescription(section: SettingsSection) {
  return {
    general: "Manage your workspace details and preferences.",
    appearance: "Adjust typography density for navigation, tables, and workspace content.",
    team: "Invite teammates, manage workspace roles, and organize ticket routing teams.",
    sla: "Set first-response targets for each ticket priority and see deadline status in the Inbox.",
    "saved-replies": "Manage reusable responses your team can insert into the Inbox composer.",
    security: "Review active sign-in sessions for your account and revoke access you no longer use.",
    recommendations: "Control how the AI assistant recommends products from your catalog.",
    widget: "Configure the storefront chat experience and its allowed origins.",
    shopify: "Connect and manage your Shopify store integration.",
  }[section];
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <label className="form-label block space-y-1.5"><span>{label}</span>{children}{error && <span className="helper-text block text-red-600">{error}</span>}</label>;
}
