"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { ArrowLeft, ArrowRight, Plus, Search, Ticket as TicketIcon } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { createTicket, listTickets } from "../api/ticket-api";
import { createTicketSchema } from "../schemas/ticket.schema";
import { listCustomersForTicket } from "@/features/customers/api/customer-api";

export default function TicketsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [page, setPage] = useState(0);
  const queryClient = useQueryClient();
  const params = useMemo(() => {
    const query = new URLSearchParams({ limit: "10", offset: String(page * 10) });
    if (search.trim()) query.set("search", search.trim());
    if (status) query.set("status", status);
    if (priority) query.set("priority", priority);
    return query.toString();
  }, [page, priority, search, status]);
  const tickets = useQuery({ queryKey: ["tickets", params], queryFn: () => listTickets(params) });
  const customers = useQuery({ queryKey: ["customers", "ticket-form"], queryFn: listCustomersForTicket });
  const form = useForm<z.infer<typeof createTicketSchema>>({ resolver: zodResolver(createTicketSchema), defaultValues: { priority: "normal" } });
  const create = useMutation({
    mutationFn: createTicket,
    onSuccess: async () => {
      form.reset({ priority: "normal" });
      await queryClient.invalidateQueries({ queryKey: ["tickets"] });
      await queryClient.invalidateQueries({ queryKey: ["ticket-stats"] });
    },
  });
  const pages = Math.max(1, Math.ceil((tickets.data?.total ?? 0) / 10));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-semibold text-blue-700">Support queue</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Tickets</h1><p className="mt-2 text-sm text-slate-500">Keep every customer conversation moving.</p></div><a href="#new-ticket"><Button><Plus size={17}/> New ticket</Button></a></div>
      <details id="new-ticket" className="group rounded-2xl border border-blue-100 bg-blue-50/70 open:bg-white open:shadow-sm">
        <summary className="flex cursor-pointer list-none items-center gap-3 p-4 text-sm font-semibold text-blue-800"><span className="grid size-9 place-items-center rounded-xl bg-white"><Plus size={17}/></span>Create a ticket<span className="ml-auto text-xs font-medium text-blue-600 group-open:hidden">Open form</span></summary>
        <form className="grid gap-4 border-t border-slate-100 p-5 md:grid-cols-2" onSubmit={form.handleSubmit((values) => create.mutate(values))}>
          <label className="space-y-1.5 text-sm font-medium text-slate-700">Customer<select className="min-h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm" {...form.register("customer_id")}><option value="">Select customer</option>{customers.data?.items.map((customer) => <option key={customer.id} value={customer.id}>{customer.name} · {customer.email}</option>)}</select>{form.formState.errors.customer_id && <span className="block text-xs text-red-600">{form.formState.errors.customer_id.message}</span>}</label>
          <label className="space-y-1.5 text-sm font-medium text-slate-700">Priority<Select {...form.register("priority")}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></Select></label>
          <label className="space-y-1.5 text-sm font-medium text-slate-700 md:col-span-2">Subject<Input placeholder="What does the customer need help with?" {...form.register("subject")}/>{form.formState.errors.subject && <span className="block text-xs text-red-600">{form.formState.errors.subject.message}</span>}</label>
          <label className="space-y-1.5 text-sm font-medium text-slate-700 md:col-span-2">Description<Textarea placeholder="Add a few details to help your team get started." {...form.register("description")}/></label>
          {create.isError && <p role="alert" className="text-sm text-red-700 md:col-span-2">{create.error instanceof ApiError ? create.error.message : "Ticket could not be created."}</p>}
          <div className="md:col-span-2"><Button type="submit" disabled={create.isPending || (customers.data?.items.length ?? 0) === 0}>{create.isPending ? "Creating…" : "Create ticket"}</Button>{customers.data?.items.length === 0 && <p className="mt-2 text-xs text-amber-700">Add a customer before creating a ticket.</p>}</div>
        </form>
      </details>
      <Panel>
        <PanelHeader title="All tickets" description={`${tickets.data?.total ?? 0} tickets in this view`}/>
        <PanelBody className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[minmax(220px,1fr)_180px_180px]"><div className="relative"><Search size={17} className="absolute left-3 top-3.5 text-slate-400"/><Input aria-label="Search tickets" className="pl-10" placeholder="Search tickets or customers…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }}/></div><Select aria-label="Filter by status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(0); }}><option value="">All statuses</option><option value="open">Open</option><option value="pending">Pending</option><option value="resolved">Resolved</option><option value="closed">Closed</option></Select><Select aria-label="Filter by priority" value={priority} onChange={(event) => { setPriority(event.target.value); setPage(0); }}><option value="">All priorities</option><option value="urgent">Urgent</option><option value="high">High</option><option value="normal">Normal</option><option value="low">Low</option></Select></div>
          {tickets.isError && <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">Unable to load tickets.</div>}
          {tickets.isPending ? <div className="space-y-3">{[1,2,3,4].map((item) => <div key={item} className="h-14 animate-pulse rounded-xl bg-slate-100"/>)}</div> : tickets.data?.items.length ? <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead><tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400"><th className="px-3 py-3 font-semibold">Subject</th><th className="px-3 py-3 font-semibold">Customer</th><th className="px-3 py-3 font-semibold">Status</th><th className="px-3 py-3 font-semibold">Priority</th><th className="px-3 py-3 font-semibold">Assignee</th><th className="px-3 py-3 font-semibold">Created</th></tr></thead><tbody className="divide-y divide-slate-100">{tickets.data.items.map((ticket) => <tr key={ticket.id} className="hover:bg-slate-50"><td className="px-3 py-4"><Link className="font-semibold text-slate-900 hover:text-blue-700" href={`/dashboard/tickets/${ticket.id}`}>{ticket.subject}</Link><p className="mt-1 text-xs text-slate-400">#{ticket.id.slice(0, 8)}</p></td><td className="px-3 py-4 text-slate-600">{ticket.customer_name ?? "Customer"}</td><td className="px-3 py-4"><Badge value={ticket.status}/></td><td className="px-3 py-4"><Badge value={ticket.priority}/></td><td className="px-3 py-4 text-slate-600">{ticket.assignee_name ?? "Unassigned"}</td><td className="px-3 py-4 text-slate-500">{formatDate(ticket.created_at)}</td></tr>)}</tbody></table></div> : <div className="rounded-2xl border border-dashed border-slate-200 py-14 text-center"><TicketIcon className="mx-auto text-slate-300" size={30}/><h3 className="mt-3 font-semibold">No tickets found</h3><p className="mt-1 text-sm text-slate-500">Try another search or create a new ticket.</p></div>}
          <div className="flex items-center justify-between border-t border-slate-100 pt-4"><p className="text-xs text-slate-500">Page {page + 1} of {pages}</p><div className="flex gap-2"><Button aria-label="Previous page" variant="secondary" size="sm" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}><ArrowLeft size={15}/> Previous</Button><Button aria-label="Next page" variant="secondary" size="sm" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next <ArrowRight size={15}/></Button></div></div>
        </PanelBody>
      </Panel>
    </div>
  );
}

function Badge({ value }: { value: string }) {
  const style = value === "urgent" || value === "open" ? "bg-red-50 text-red-700" : value === "high" || value === "pending" ? "bg-amber-50 text-amber-700" : value === "resolved" ? "bg-emerald-50 text-emerald-700" : value === "closed" || value === "low" ? "bg-slate-100 text-slate-600" : "bg-blue-50 text-blue-700";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${style}`}>{value}</span>;
}
