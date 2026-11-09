"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Clock3, Mail, MessageSquareText, TicketCheck, UserRoundCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getCustomerMessageHistory, listCustomerTickets } from "@/features/customers/api/customer-api";
import { listMembers } from "@/features/organization/api/organization-api";
import { listTeams, teamQueryKey } from "@/features/organization/api/team-api";
import { assignTicketToMe, getTicket, getTicketActivity, updateTicket } from "@/features/tickets/api/ticket-api";
import type { Ticket, TicketActivity } from "@/features/tickets/types/ticket.types";
import { formatDateTime } from "@/lib/utils";
import type { InboxItem } from "../types/inbox.types";

const statuses: Ticket["status"][] = ["open", "pending", "resolved", "closed"];
const priorities: Ticket["priority"][] = ["low", "normal", "high", "urgent"];

export function CustomerContextPanel({ item, role }: { item: InboxItem; role: string }) {
  const [showAllActivity, setShowAllActivity] = useState(false);
  const client = useQueryClient();
  const canEdit = ["owner", "admin", "agent"].includes(role);
  const canAssign = ["owner", "admin"].includes(role);
  const members = useQuery({ queryKey: ["users"], queryFn: listMembers, enabled: canAssign });
  const teams = useQuery({ queryKey: teamQueryKey, queryFn: listTeams, enabled: canAssign });
  const ticket = useQuery({ queryKey: ["ticket", item.ticketId], queryFn: () => getTicket(item.ticketId) });
  const tickets = useQuery({ queryKey: ["customer-tickets", item.customer.id], queryFn: () => listCustomerTickets(item.customer.id) });
  const history = useQuery({ queryKey: ["customer-message-history", item.customer.id], queryFn: () => getCustomerMessageHistory(item.customer.id) });
  const customerTickets = tickets.data && Array.isArray(tickets.data.items) ? tickets.data.items : [];
  const relatedTickets = customerTickets.filter((ticket) => ticket.id !== item.ticketId);
  const activity = useQuery({ queryKey: ["ticket-activity", item.ticketId], queryFn: () => getTicketActivity(item.ticketId) });
  const activityEntries = activity.data ? [...activity.data].reverse() : [];
  const visibleActivity = showAllActivity ? activityEntries : activityEntries.slice(0, 5);
  const update = useMutation({
    mutationFn: (changes: { status?: Ticket["status"]; priority?: Ticket["priority"]; assignee_id?: string | null; team_id?: string | null }) => updateTicket(item.ticketId, changes),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["inbox"] }),
        client.invalidateQueries({ queryKey: ["ticket", item.ticketId] }),
        client.invalidateQueries({ queryKey: ["ticket-activity", item.ticketId] }),
      ]);
    },
  });
  const claim = useMutation({
    mutationFn: () => assignTicketToMe(item.ticketId),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["inbox"] }),
        client.invalidateQueries({ queryKey: ["ticket", item.ticketId] }),
        client.invalidateQueries({ queryKey: ["ticket-activity", item.ticketId] }),
      ]);
    },
  });

  return <div className="h-full overflow-y-auto bg-muted/30 text-foreground">
    <div className="border-b border-border bg-background p-5">
      <div className="flex items-center gap-3"><span className="grid size-11 shrink-0 place-items-center rounded-full bg-violet-100 text-base font-bold text-violet-800">{item.customer.name.trim().slice(0, 1).toUpperCase()}</span><div className="min-w-0"><h2 className="truncate font-semibold">{item.customer.name}</h2><p className="truncate text-xs text-muted-foreground">{item.customer.email ?? "No email address"}</p></div></div>
      <Link href={`/dashboard/customers/${item.customer.id}`} className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">Customer profile <ArrowUpRight size={13}/></Link>
      {item.customer.email && <Link href={`/dashboard/orders?email=${encodeURIComponent(item.customer.email)}`} className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">Verify Shopify order <ArrowUpRight size={13}/></Link>}
    </div>

    <div className="space-y-4 p-4">
      <Panel className="border-border shadow-none">
        <PanelHeader title="Ticket details" description={`Updated ${formatDateTime(item.updatedAt)}`}/>
        <PanelBody className="space-y-4">
          <div><label htmlFor="inbox-ticket-status" className="mb-1.5 block text-xs font-semibold text-muted-foreground">Status</label><Select id="inbox-ticket-status" value={item.status} disabled={!canEdit || update.isPending} onChange={(event) => update.mutate({ status: event.target.value as Ticket["status"] })}>{statuses.map((status) => <option key={status} value={status}>{titleCase(status)}</option>)}</Select></div>
          <div><label htmlFor="inbox-ticket-priority" className="mb-1.5 block text-xs font-semibold text-muted-foreground">Priority</label><Select id="inbox-ticket-priority" value={item.priority} disabled={!canEdit || update.isPending} onChange={(event) => update.mutate({ priority: event.target.value as Ticket["priority"] })}>{priorities.map((priority) => <option key={priority} value={priority}>{titleCase(priority)}</option>)}</Select></div>
          <div><label htmlFor="inbox-ticket-team" className="mb-1.5 block text-xs font-semibold text-muted-foreground">Team</label><Select id="inbox-ticket-team" value={ticket.data?.team_id ?? ""} disabled={!canAssign || update.isPending || ticket.isPending || teams.isPending} onChange={(event) => update.mutate({ team_id: event.target.value || null, assignee_id: null })}><option value="">No team</option>{teams.data?.filter((team) => team.is_active || team.id === ticket.data?.team_id).map((team) => <option key={team.id} value={team.id} disabled={!team.is_active}>{team.name}{team.is_active ? "" : " · inactive"}</option>)}</Select>{canAssign && item.assignee && <p className="mt-1 text-[11px] text-muted-foreground">Changing the team clears the current assignee.</p>}</div>
          <div><label htmlFor="inbox-ticket-assignee" className="mb-1.5 block text-xs font-semibold text-muted-foreground">Assignee</label><Select id="inbox-ticket-assignee" value={item.assignee?.id ?? ""} disabled={!canAssign || update.isPending || members.isPending} onChange={(event) => update.mutate({ assignee_id: event.target.value || null })}><option value="">Unassigned</option>{members.data?.filter((member) => member.is_active && ["owner", "admin", "agent"].includes(member.role) && (!ticket.data?.team_id || teams.data?.find((team) => team.id === ticket.data?.team_id)?.members.some((teamMember) => teamMember.id === member.id))).map((member) => <option key={member.id} value={member.id}>{member.full_name} · {member.role}</option>)}</Select>{!canAssign && <p className="mt-1 text-xs text-muted-foreground/70">Only Owners and Admins can choose a team or another assignee.</p>}</div>
          {canEdit && !item.assignee && <Button type="button" variant="secondary" className="w-full" disabled={claim.isPending} onClick={() => claim.mutate()}><UserRoundCheck size={15}/>{claim.isPending ? "Claiming…" : "Assign to me"}</Button>}
          {update.isError && <p role="alert" className="rounded-md bg-destructive/10 p-3 text-xs text-destructive">{update.error instanceof Error ? update.error.message : "Ticket could not be updated."}</p>}
          {claim.isError && <p role="alert" className="rounded-md bg-destructive/10 p-3 text-xs text-destructive">{claim.error instanceof Error ? claim.error.message : "Ticket could not be claimed."}</p>}
        </PanelBody>
      </Panel>

      <details className="rounded-none border-0 border-b border-border bg-background shadow-none">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3.5 text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><span className="flex items-center gap-2"><TicketCheck size={16} className="text-muted-foreground/70"/>Recent tickets</span><span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">{relatedTickets.length}</span></summary>
        <div className="space-y-3 border-t border-border/60 p-3">
          {tickets.isPending && <div className="h-14 animate-pulse rounded-md bg-muted"/>}
          {tickets.isError && <p role="alert" className="text-xs text-destructive">Customer history could not be loaded.</p>}
          {relatedTickets.slice(0, 4).map((ticket) => <Link key={ticket.id} href={`/dashboard/tickets/${ticket.id}`} className="block rounded-md p-2 hover:bg-muted/60"><p className="truncate text-sm font-medium text-foreground">{ticket.subject}</p><p className="mt-1 text-xs capitalize text-muted-foreground">{ticket.status} · {titleCase(ticket.priority)}</p></Link>)}
          {tickets.data && relatedTickets.length === 0 && <p className="text-xs text-muted-foreground">No other customer tickets.</p>}
        </div>
      </details>

      <details className="rounded-none border-0 border-b border-border bg-background shadow-none" open>
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3.5 text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><span className="flex items-center gap-2"><MessageSquareText size={16} className="text-muted-foreground/70"/>Recent messages</span><span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">{history.data?.items.length ?? 0}</span></summary>
        <div className="space-y-3 border-t border-border/60 p-3">
          {history.isPending && <div className="h-20 animate-pulse rounded-md bg-muted"/>}
          {history.isError && <p role="alert" className="text-xs text-destructive">Customer message history could not be loaded.</p>}
          {history.data?.items.slice(0, 4).map((message) => <article key={message.id} className="rounded-md bg-muted/30 p-3">
            <div className="flex items-start justify-between gap-2"><Link href={`/dashboard/tickets/${message.ticket_id}`} className="min-w-0 truncate text-xs font-semibold text-primary hover:underline">{message.ticket_subject}</Link><time className="shrink-0 text-[10px] text-muted-foreground/70">{formatDateTime(message.created_at)}</time></div>
            <p className="mt-1 text-[11px] text-muted-foreground">{message.sender_name ?? (message.sender_type === "customer" ? item.customer.name : "SupportPilot")} · {message.sender_type === "customer" ? "Customer" : "Team reply"}</p>
            <p className="mt-2 line-clamp-3 whitespace-pre-wrap break-words text-xs leading-5 text-foreground/90">{message.content}</p>
          </article>)}
          {history.data?.items.length === 0 && <p className="text-xs text-muted-foreground">No earlier messages from this customer.</p>}
          {history.data && history.data.total > 4 && <Link href={`/dashboard/customers/${item.customer.id}`} className="inline-flex items-center gap-1 px-1 text-xs font-semibold text-primary hover:underline">View all {history.data.total} messages <ArrowUpRight size={12}/></Link>}
        </div>
      </details>

      <details className="rounded-none border-0 border-b border-border bg-background shadow-none">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3.5 text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><span className="flex items-center gap-2"><Clock3 size={16} className="text-muted-foreground/70"/>Activity timeline</span><span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">{activity.data?.length ?? 0}</span></summary>
        <div className="space-y-3 border-t border-border/60 p-3">
          {activity.isPending && <div className="h-14 animate-pulse rounded-md bg-muted"/>}
          {activity.isError && <p role="alert" className="text-xs text-destructive">Activity could not be loaded.</p>}
          {visibleActivity.map((entry) => <div key={entry.id} className="flex gap-2"><span className="mt-1 size-2 shrink-0 rounded-full bg-primary/50"/><div><p className="text-xs font-medium text-foreground/90">{activityLabel(entry.activity_type, entry.details)}</p><p className="mt-1 text-[11px] text-muted-foreground/70">{entry.actor_name ?? "System"} · {formatDateTime(entry.created_at)}</p></div></div>)}
          {activity.data?.length === 0 && <p className="text-xs text-muted-foreground">No activity recorded yet.</p>}
          {(activity.data?.length ?? 0) > 5 && <Button variant="unstyled" type="button" aria-expanded={showAllActivity} onClick={() => setShowAllActivity((current) => !current)} className="rounded px-1 text-xs font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{showAllActivity ? "Show latest 5" : `View all ${activity.data?.length} events`}</Button>}
        </div>
      </details>

      {item.customer.email && <a href={`mailto:${item.customer.email}`} className="inline-flex items-center gap-2 px-1 text-xs font-semibold text-muted-foreground hover:text-primary"><Mail size={14}/> Email customer</a>}
    </div>
  </div>;
}

function titleCase(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function activityLabel(type: string, details: TicketActivity["details"]) {
  if (type === "created") return "Ticket created";
  if (type === "automation_retry_requested") return `Automation retry queued · attempt ${String(details.attempt_count ?? "")}`;
  const keys = Object.keys(details).map((key) => key.replaceAll("_", " "));
  return keys.length ? `Updated ${keys.join(", ")}` : "Ticket updated";
}
