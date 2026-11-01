"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Clock3, Mail, TicketCheck, UserRoundCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { listCustomerTickets } from "@/features/customers/api/customer-api";
import { listMembers } from "@/features/organization/api/organization-api";
import { assignTicketToMe, getTicketActivity, updateTicket } from "@/features/tickets/api/ticket-api";
import type { Ticket, TicketActivity } from "@/features/tickets/types/ticket.types";
import { formatDateTime } from "@/lib/utils";
import type { InboxItem } from "../types/inbox.types";

const statuses: Ticket["status"][] = ["open", "pending", "resolved", "closed"];
const priorities: Ticket["priority"][] = ["low", "normal", "high", "urgent"];

export function CustomerContextPanel({ item, role }: { item: InboxItem; role: string }) {
  const client = useQueryClient();
  const canEdit = ["owner", "admin", "agent"].includes(role);
  const canAssign = ["owner", "admin"].includes(role);
  const members = useQuery({ queryKey: ["users"], queryFn: listMembers, enabled: canAssign });
  const tickets = useQuery({ queryKey: ["customer-tickets", item.customer.id], queryFn: () => listCustomerTickets(item.customer.id) });
  const relatedTickets = tickets.data?.items.filter((ticket) => ticket.id !== item.ticketId) ?? [];
  const activity = useQuery({ queryKey: ["ticket-activity", item.ticketId], queryFn: () => getTicketActivity(item.ticketId) });
  const update = useMutation({
    mutationFn: (changes: { status?: Ticket["status"]; priority?: Ticket["priority"]; assignee_id?: string | null }) => updateTicket(item.ticketId, changes),
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

  return <div className="h-full overflow-y-auto bg-slate-50 text-slate-900">
    <div className="border-b border-slate-200 bg-white p-5">
      <div className="flex items-center gap-3"><span className="grid size-11 shrink-0 place-items-center rounded-full bg-violet-100 text-base font-bold text-violet-800">{item.customer.name.trim().slice(0, 1).toUpperCase()}</span><div className="min-w-0"><h2 className="truncate font-semibold">{item.customer.name}</h2><p className="truncate text-xs text-slate-500">{item.customer.email ?? "No email address"}</p></div></div>
      <Link href={`/dashboard/customers/${item.customer.id}`} className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-blue-700 hover:underline">Customer profile <ArrowUpRight size={13}/></Link>
      {item.customer.email && <Link href={`/dashboard/orders?email=${encodeURIComponent(item.customer.email)}`} className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-blue-700 hover:underline">Verify Shopify order <ArrowUpRight size={13}/></Link>}
    </div>

    <div className="space-y-4 p-4">
      <Panel className="border-slate-200 shadow-sm">
        <PanelHeader title="Ticket details" description={`Updated ${formatDateTime(item.updatedAt)}`}/>
        <PanelBody className="space-y-4">
          <div><label htmlFor="inbox-ticket-status" className="mb-1.5 block text-xs font-semibold text-slate-500">Status</label><Select id="inbox-ticket-status" value={item.status} disabled={!canEdit || update.isPending} onChange={(event) => update.mutate({ status: event.target.value as Ticket["status"] })}>{statuses.map((status) => <option key={status} value={status}>{titleCase(status)}</option>)}</Select></div>
          <div><label htmlFor="inbox-ticket-priority" className="mb-1.5 block text-xs font-semibold text-slate-500">Priority</label><Select id="inbox-ticket-priority" value={item.priority} disabled={!canEdit || update.isPending} onChange={(event) => update.mutate({ priority: event.target.value as Ticket["priority"] })}>{priorities.map((priority) => <option key={priority} value={priority}>{titleCase(priority)}</option>)}</Select></div>
          <div><label htmlFor="inbox-ticket-assignee" className="mb-1.5 block text-xs font-semibold text-slate-500">Assignee</label><Select id="inbox-ticket-assignee" value={item.assignee?.id ?? ""} disabled={!canAssign || update.isPending || members.isPending} onChange={(event) => update.mutate({ assignee_id: event.target.value || null })}><option value="">Unassigned</option>{members.data?.filter((member) => member.is_active && ["owner", "admin", "agent"].includes(member.role)).map((member) => <option key={member.id} value={member.id}>{member.full_name} · {member.role}</option>)}</Select>{!canAssign && <p className="mt-1 text-xs text-slate-400">Only Owners and Admins can choose another assignee.</p>}</div>
          {canEdit && !item.assignee && <Button type="button" variant="secondary" className="w-full" disabled={claim.isPending} onClick={() => claim.mutate()}><UserRoundCheck size={15}/>{claim.isPending ? "Claiming…" : "Assign to me"}</Button>}
          {update.isError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-xs text-red-700">{update.error instanceof Error ? update.error.message : "Ticket could not be updated."}</p>}
          {claim.isError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-xs text-red-700">{claim.error instanceof Error ? claim.error.message : "Ticket could not be claimed."}</p>}
        </PanelBody>
      </Panel>

      <details className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3.5 text-sm font-semibold text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"><span className="flex items-center gap-2"><TicketCheck size={16} className="text-slate-400"/>Recent tickets</span><span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">{relatedTickets.length}</span></summary>
        <div className="space-y-3 border-t border-slate-100 p-3">
          {tickets.isPending && <div className="h-14 animate-pulse rounded-lg bg-slate-100"/>}
          {tickets.isError && <p role="alert" className="text-xs text-red-700">Customer history could not be loaded.</p>}
          {relatedTickets.slice(0, 4).map((ticket) => <Link key={ticket.id} href={`/dashboard/tickets/${ticket.id}`} className="block rounded-lg p-2 hover:bg-slate-50"><p className="truncate text-sm font-medium text-slate-800">{ticket.subject}</p><p className="mt-1 text-xs capitalize text-slate-500">{ticket.status} · {titleCase(ticket.priority)}</p></Link>)}
          {tickets.data && relatedTickets.length === 0 && <p className="text-xs text-slate-500">No other customer tickets.</p>}
        </div>
      </details>

      <details className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3.5 text-sm font-semibold text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"><span className="flex items-center gap-2"><Clock3 size={16} className="text-slate-400"/>Activity timeline</span><span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">{activity.data?.length ?? 0}</span></summary>
        <div className="space-y-3 border-t border-slate-100 p-3">
          {activity.isPending && <div className="h-14 animate-pulse rounded-lg bg-slate-100"/>}
          {activity.isError && <p role="alert" className="text-xs text-red-700">Activity could not be loaded.</p>}
          {activity.data?.slice(0, 5).map((entry) => <div key={entry.id} className="flex gap-2"><span className="mt-1 size-2 shrink-0 rounded-full bg-blue-500"/><div><p className="text-xs font-medium text-slate-700">{activityLabel(entry.activity_type, entry.details)}</p><p className="mt-1 text-[11px] text-slate-400">{entry.actor_name ?? "System"} · {formatDateTime(entry.created_at)}</p></div></div>)}
          {activity.data?.length === 0 && <p className="text-xs text-slate-500">No activity recorded yet.</p>}
        </div>
      </details>

      {item.customer.email && <a href={`mailto:${item.customer.email}`} className="inline-flex items-center gap-2 px-1 text-xs font-semibold text-slate-500 hover:text-blue-700"><Mail size={14}/> Email customer</a>}
    </div>
  </div>;
}

function titleCase(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function activityLabel(type: string, details: TicketActivity["details"]) {
  if (type === "created") return "Ticket created";
  const keys = Object.keys(details).map((key) => key.replaceAll("_", " "));
  return keys.length ? `Updated ${keys.join(", ")}` : "Ticket updated";
}
