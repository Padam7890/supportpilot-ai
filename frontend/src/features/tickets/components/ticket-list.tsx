"use client";

import { Checkbox } from "@/components/ui";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Ellipsis, Pencil, Plus, Search, Ticket as TicketIcon } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { Input, Select } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { bulkUpdateTickets, listTickets, type BulkTicketChanges } from "../api/ticket-api";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { listMembers } from "@/features/organization/api/organization-api";
import { listTeams, teamQueryKey } from "@/features/organization/api/team-api";
import type { Ticket } from "../types/ticket.types";
import { TicketFormDrawer } from "./ticket-form-drawer";

const MAX_BULK_TICKETS = 100;

export default function TicketsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkStatus, setBulkStatus] = useState("");
  const [bulkPriority, setBulkPriority] = useState("");
  const [bulkAssignee, setBulkAssignee] = useState("__unchanged");
  const [bulkTeam, setBulkTeam] = useState("__unchanged");
  const [bulkNotice, setBulkNotice] = useState<{ message: string; tone: "success" | "limit" } | null>(null);
  const [ticketDrawerOpen, setTicketDrawerOpen] = useState(false);
  const [editingTicket, setEditingTicket] = useState<Ticket | null>(null);
  const queryClient = useQueryClient();
  const params = useMemo(() => {
    const query = new URLSearchParams({ limit: "10", offset: String(page * 10) });
    if (search.trim()) query.set("search", search.trim());
    if (status) query.set("status", status);
    if (priority) query.set("priority", priority);
    return query.toString();
  }, [page, priority, search, status]);
  const tickets = useQuery({ queryKey: ["tickets", params], queryFn: () => listTickets(params) });
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const canAssign = me.data?.role === "owner" || me.data?.role === "admin";
  const members = useQuery({ queryKey: ["users"], queryFn: listMembers, enabled: canAssign && selectedIds.length > 0 });
  const teams = useQuery({ queryKey: teamQueryKey, queryFn: listTeams, enabled: canAssign });
  const bulkUpdate = useMutation({
    mutationFn: bulkUpdateTickets,
    onSuccess: async (result) => {
      setBulkNotice({ message: `${result.changed_count} of ${result.updated_count} selected tickets updated.`, tone: "success" });
      setSelectedIds([]);
      setBulkStatus("");
      setBulkPriority("");
      setBulkAssignee("__unchanged");
      setBulkTeam("__unchanged");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tickets"] }),
        queryClient.invalidateQueries({ queryKey: ["inbox"] }),
        queryClient.invalidateQueries({ queryKey: ["ticket-stats"] }),
      ]);
    },
  });
  const pages = Math.max(1, Math.ceil((tickets.data?.total ?? 0) / 10));
  const pageTicketIds = tickets.data?.items.map((ticket) => ticket.id) ?? [];
  const allPageSelected = pageTicketIds.length > 0 && pageTicketIds.every((id) => selectedIds.includes(id));
  const hasBulkChanges = Boolean(bulkStatus || bulkPriority || (canAssign && (bulkAssignee !== "__unchanged" || bulkTeam !== "__unchanged")));

  function submitBulkUpdate() {
    const changes: BulkTicketChanges = { ticket_ids: selectedIds };
    if (bulkStatus) changes.status = bulkStatus as NonNullable<BulkTicketChanges["status"]>;
    if (bulkPriority) changes.priority = bulkPriority as NonNullable<BulkTicketChanges["priority"]>;
    if (canAssign && bulkAssignee !== "__unchanged") changes.assignee_id = bulkAssignee || null;
    if (canAssign && bulkTeam !== "__unchanged") changes.team_id = bulkTeam || null;
    setBulkNotice(null);
    bulkUpdate.mutate(changes);
  }

  function toggleTicketSelection(ticketId: string, selected: boolean) {
    setBulkNotice(null);
    if (!selected) {
      setSelectedIds(selectedIds.filter((id) => id !== ticketId));
      return;
    }
    if (selectedIds.includes(ticketId)) return;
    if (selectedIds.length >= MAX_BULK_TICKETS) {
      setBulkNotice({ message: `Bulk actions are limited to ${MAX_BULK_TICKETS} tickets. Clear some selections to add this ticket.`, tone: "limit" });
      return;
    }
    setSelectedIds([...selectedIds, ticketId]);
  }

  function togglePageSelection(selected: boolean) {
    setBulkNotice(null);
    if (!selected) {
      setSelectedIds(selectedIds.filter((id) => !pageTicketIds.includes(id)));
      return;
    }
    const next = Array.from(new Set([...selectedIds, ...pageTicketIds]));
    if (next.length > MAX_BULK_TICKETS) {
      setBulkNotice({ message: `Select up to ${MAX_BULK_TICKETS} tickets across pages. This page was not added because it would exceed the limit.`, tone: "limit" });
      return;
    }
    setSelectedIds(next);
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Support queue" title="Tickets" description="Keep every customer conversation moving." actions={<Button onClick={() => { setEditingTicket(null); setTicketDrawerOpen(true); }}><Plus size={17}/> New ticket</Button>} />
      <Panel>
        <PanelHeader title="All tickets" description={`${tickets.data?.total ?? 0} tickets in this view`}/>
        <PanelBody className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[minmax(220px,1fr)_180px_180px]"><div className="relative"><Search size={17} className="absolute left-3 top-3.5 text-slate-400"/><Input aria-label="Search tickets" className="pl-10" placeholder="Search tickets or customers…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); setSelectedIds([]); }}/></div><Select aria-label="Filter by status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(0); setSelectedIds([]); }}><option value="">All statuses</option><option value="open">Open</option><option value="pending">Pending</option><option value="resolved">Resolved</option><option value="closed">Closed</option></Select><Select aria-label="Filter by priority" value={priority} onChange={(event) => { setPriority(event.target.value); setPage(0); setSelectedIds([]); }}><option value="">All priorities</option><option value="urgent">Urgent</option><option value="high">High</option><option value="normal">Normal</option><option value="low">Low</option></Select></div>
          {bulkNotice && <p role="status" className={`text-sm font-medium ${bulkNotice.tone === "limit" ? "text-amber-800" : "text-emerald-700"}`}>{bulkNotice.message}</p>}
          {selectedIds.length > 0 && <section aria-label="Bulk ticket actions" className="space-y-4 rounded-lg border border-border bg-muted/20 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-sm font-semibold tabular-nums text-primary">{selectedIds.length}</span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">Bulk update</p>
                  <p className="text-xs text-muted-foreground">Selected tickets across pages · up to {MAX_BULK_TICKETS}</p>
                </div>
              </div>
              <Button size="sm" variant="ghost" disabled={bulkUpdate.isPending} onClick={() => setSelectedIds([])}>Clear selection</Button>
            </div>
            <div className={`grid grid-cols-1 gap-3 sm:grid-cols-2 ${canAssign ? "xl:grid-cols-4" : "xl:grid-cols-2"}`}>
              <label className="block space-y-1.5 text-xs font-medium text-muted-foreground">Status
                <Select aria-label="Bulk status change" className="h-9 bg-background text-sm text-foreground" value={bulkStatus} onChange={(event) => setBulkStatus(event.target.value)}><option value="">Keep current status</option><option value="open">Open</option><option value="pending">Pending</option><option value="resolved">Resolved</option><option value="closed">Closed</option></Select>
              </label>
              <label className="block space-y-1.5 text-xs font-medium text-muted-foreground">Priority
                <Select aria-label="Bulk priority change" className="h-9 bg-background text-sm text-foreground" value={bulkPriority} onChange={(event) => setBulkPriority(event.target.value)}><option value="">Keep current priority</option><option value="urgent">Urgent</option><option value="high">High</option><option value="normal">Normal</option><option value="low">Low</option></Select>
              </label>
              {canAssign && <label className="block space-y-1.5 text-xs font-medium text-muted-foreground">Assignee
                <Select aria-label="Bulk assignee change" className="h-9 bg-background text-sm text-foreground" value={bulkAssignee} onChange={(event) => setBulkAssignee(event.target.value)}><option value="__unchanged">Keep current assignee</option><option value="">Unassign</option>{members.data?.filter((member) => member.is_active && ["owner", "admin", "agent"].includes(member.role)).map((member) => <option key={member.id} value={member.id}>{member.full_name} · {member.role}</option>)}</Select>
              </label>}
              {canAssign && <label className="block space-y-1.5 text-xs font-medium text-muted-foreground">Team
                <Select aria-label="Bulk team routing" className="h-9 bg-background text-sm text-foreground" value={bulkTeam} onChange={(event) => setBulkTeam(event.target.value)}><option value="__unchanged">Keep current team</option><option value="">No team</option>{teams.data?.filter((team) => team.is_active).map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</Select>
              </label>}
            </div>
            <div className="flex flex-col gap-3 border-t border-border pt-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 space-y-1">
                {canAssign && bulkTeam !== "__unchanged" && bulkTeam && <p className="text-xs text-muted-foreground">Existing assignees must belong to the selected team. Update assignees separately if needed.</p>}
                {bulkUpdate.isError && <p role="alert" className="text-sm text-destructive">{bulkUpdate.error instanceof ApiError ? bulkUpdate.error.message : "Selected tickets could not be updated."}</p>}
              </div>
              <Button size="sm" className="shrink-0" disabled={!hasBulkChanges || bulkUpdate.isPending} onClick={submitBulkUpdate}>{bulkUpdate.isPending ? "Updating…" : "Apply changes"}</Button>
            </div>
          </section>}
          {tickets.isError && <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">Unable to load tickets.</div>}
          {tickets.isPending ? <div className="space-y-3">{[1,2,3,4].map((item) => <div key={item} className="h-14 animate-pulse rounded-xl bg-muted"/>)}</div> : tickets.data?.items.length ? <div className="overflow-x-auto rounded-lg border border-border"><table className="w-full min-w-[820px] text-left text-sm"><thead><tr className="border-b border-border bg-muted/30 text-xs uppercase tracking-wide text-muted-foreground"><th className="w-10 px-3 py-3"><Checkbox aria-label="Select all tickets on this page" checked={allPageSelected} onCheckedChange={(checked) => togglePageSelection(checked === true)}/></th><th className="px-3 py-3 font-semibold">Subject</th><th className="px-3 py-3 font-semibold">Customer</th><th className="px-3 py-3 font-semibold">Status</th><th className="px-3 py-3 font-semibold">Priority</th><th className="px-3 py-3 font-semibold">Assignment</th><th className="px-3 py-3 font-semibold">Created</th><th className="w-12 px-3 py-3"><span className="sr-only">Actions</span></th></tr></thead><tbody className="divide-y divide-border">{tickets.data.items.map((ticket) => <tr key={ticket.id} className="transition-colors hover:bg-muted/30"><td className="px-3 py-3"><Checkbox aria-label={`Select ticket ${ticket.subject}`} checked={selectedIds.includes(ticket.id)} onCheckedChange={(checked) => toggleTicketSelection(ticket.id, checked === true)}/></td><td className="px-3 py-3"><Link className="font-medium text-foreground hover:text-primary" href={`/dashboard/tickets/${ticket.id}`}>{ticket.subject}</Link><p className="mt-1 text-xs text-muted-foreground">#{ticket.id.slice(0, 8)}</p></td><td className="px-3 py-3 text-muted-foreground">{ticket.customer_name ?? "Customer"}</td><td className="px-3 py-3"><Badge value={ticket.status}/></td><td className="px-3 py-3"><Badge value={ticket.priority}/></td><td className="px-3 py-3 text-muted-foreground"><span className="block">{ticket.assignee_name ?? "Unassigned"}</span>{ticket.team_name && <span className="mt-1 block text-xs text-muted-foreground">{ticket.team_name}</span>}</td><td className="px-3 py-3 text-muted-foreground">{formatDate(ticket.created_at)}</td><td className="px-3 py-3" onClick={(event) => event.stopPropagation()}><DropdownMenu><DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${ticket.subject}`} title="Ticket actions"/>}><Ellipsis size={16}/></DropdownMenuTrigger><DropdownMenuContent align="end" className="w-40"><DropdownMenuItem onClick={() => { setEditingTicket(ticket); setTicketDrawerOpen(true); }}><Pencil size={14}/>Edit ticket</DropdownMenuItem></DropdownMenuContent></DropdownMenu></td></tr>)}</tbody></table></div> : <div className="rounded-lg border border-dashed border-border py-14 text-center"><TicketIcon className="mx-auto text-muted-foreground/50" size={30}/><h3 className="mt-3 font-semibold text-foreground">No tickets found</h3><p className="mt-1 text-sm text-muted-foreground">Try another search or create a new ticket.</p></div>}
          <div className="flex items-center justify-between border-t border-slate-100 pt-4"><p className="text-xs text-slate-500">Page {page + 1} of {pages}</p><div className="flex gap-2"><Button aria-label="Previous page" variant="secondary" size="sm" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}><ArrowLeft size={15}/> Previous</Button><Button aria-label="Next page" variant="secondary" size="sm" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next <ArrowRight size={15}/></Button></div></div>
        </PanelBody>
      </Panel>
      <TicketFormDrawer open={ticketDrawerOpen} onOpenChange={setTicketDrawerOpen} ticket={editingTicket}/>
    </div>
  );
}

function Badge({ value }: { value: string }) {
  const style = value === "urgent" || value === "open" ? "bg-red-50 text-red-700" : value === "high" || value === "pending" ? "bg-amber-50 text-amber-700" : value === "resolved" ? "bg-emerald-50 text-emerald-700" : value === "closed" || value === "low" ? "bg-slate-100 text-slate-600" : "bg-blue-50 text-blue-700";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${style}`}>{value}</span>;
}
