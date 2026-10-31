"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, Mail, Phone, Ticket as TicketIcon } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getCustomer, getCustomerMessageHistory, listCustomerTickets, updateCustomer } from "../api/customer-api";
import { updateCustomerSchema } from "../schemas/customer.schema";

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const queryClient = useQueryClient();
  const customer = useQuery({ queryKey: ["customer", id], queryFn: () => getCustomer(id) });
  const tickets = useQuery({ queryKey: ["customer-tickets", id], queryFn: () => listCustomerTickets(id) });
  const history = useQuery({ queryKey: ["customer-message-history", id], queryFn: () => getCustomerMessageHistory(id) });
  const form = useForm<z.infer<typeof updateCustomerSchema>>({ resolver: zodResolver(updateCustomerSchema) });
  useEffect(() => {
    if (customer.data) form.reset({ name: customer.data.name, email: customer.data.email, phone: customer.data.phone ?? "", external_reference: customer.data.external_reference ?? "" });
  }, [customer.data, form]);
  const update = useMutation({
    mutationFn: (values: z.infer<typeof updateCustomerSchema>) => updateCustomer(id, values),
    onSuccess: async (saved) => { queryClient.setQueryData(["customer", id], saved); await queryClient.invalidateQueries({ queryKey: ["customers"] }); },
  });

  if (customer.isPending) return <div className="h-64 animate-pulse rounded-2xl bg-white"/>;
  if (customer.isError || !customer.data) return <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">Customer not found or unavailable. <Link href="/dashboard/customers" className="font-semibold underline">Back to customers</Link></div>;
  return (
    <div className="space-y-6">
      <Link href="/dashboard/customers" className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900"><ArrowLeft size={16}/> Customers</Link>
      <div><p className="text-sm font-semibold text-blue-700">Customer profile</p><h1 className="mt-1 text-3xl font-bold tracking-tight">{customer.data.name}</h1><p className="mt-2 text-sm text-slate-500">Added {formatDate(customer.data.created_at)}</p></div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <Panel><PanelHeader title="Contact details" description="Keep this customer information up to date."/><PanelBody><form className="space-y-4" onSubmit={form.handleSubmit((values) => update.mutate(values))}>
          <Field label="Full name" error={form.formState.errors.name?.message}><Input {...form.register("name")}/></Field>
          <Field label="Email" error={form.formState.errors.email?.message}><Input type="email" {...form.register("email")}/></Field>
          <Field label="Phone" error={form.formState.errors.phone?.message}><Input type="tel" {...form.register("phone")}/></Field>
          <Field label="External reference" error={form.formState.errors.external_reference?.message}><Input {...form.register("external_reference")}/></Field>
          {update.isError && <p role="alert" className="text-sm text-red-700">{update.error instanceof ApiError ? update.error.message : "Could not update customer."}</p>}
          {update.isSuccess && <p role="status" className="text-sm text-emerald-700">Customer details saved.</p>}
          <Button type="submit" disabled={update.isPending}>{update.isPending ? "Saving…" : "Save changes"}</Button>
        </form></PanelBody></Panel>
        <Panel><PanelHeader title="Ticket history" description={`${tickets.data?.total ?? 0} support requests`}/><PanelBody>
          {tickets.isPending ? <div className="h-40 animate-pulse rounded-xl bg-slate-100"/> : tickets.isError ? <p role="alert" className="text-sm text-red-700">Unable to load ticket history.</p> : tickets.data?.items.length ? <div className="divide-y divide-slate-100">{tickets.data.items.map((ticket) => <Link key={ticket.id} href={`/dashboard/tickets/${ticket.id}`} className="flex items-center gap-3 py-4 first:pt-0 last:pb-0"><span className="grid size-10 place-items-center rounded-xl bg-blue-50 text-blue-700"><TicketIcon size={18}/></span><span className="min-w-0 flex-1"><span className="block truncate font-semibold text-slate-900">{ticket.subject}</span><span className="mt-1 block text-xs capitalize text-slate-500">{ticket.status} · {ticket.priority} priority · {formatDate(ticket.created_at)}</span></span><span className="text-blue-700">→</span></Link>)}</div> : <div className="rounded-xl bg-slate-50 p-7 text-center"><TicketIcon size={25} className="mx-auto text-slate-300"/><p className="mt-2 text-sm font-medium text-slate-700">No tickets yet</p></div>}
        </PanelBody></Panel>
      </div>
      <Panel><PanelHeader title="Recent message history" description="Earlier customer and teammate messages across this customer’s conversations."/><PanelBody>
        {history.isPending ? <div className="h-28 animate-pulse rounded-xl bg-slate-100"/> : history.isError ? <p role="alert" className="text-sm text-red-700">Message history could not be loaded.</p> : history.data?.items.length ? <div className="divide-y divide-slate-100">{history.data.items.map((message) => <article key={message.id} className="py-4 first:pt-0 last:pb-0"><div className="flex flex-wrap items-center justify-between gap-2"><Link href={`/dashboard/tickets/${message.ticket_id}`} className="text-sm font-semibold text-blue-700 hover:underline">{message.ticket_subject}</Link><time className="text-xs text-slate-400">{formatDate(message.created_at)}</time></div><p className="mt-1 text-xs text-slate-500">{message.sender_name ?? (message.sender_type === "customer" ? customer.data.name : "SupportPilot")} · {message.sender_type === "customer" ? "Customer" : "Team reply"}</p><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{message.content}</p></article>)}</div> : <p className="rounded-xl bg-slate-50 p-6 text-center text-sm text-slate-500">No earlier conversation messages yet.</p>}
        {history.data && history.data.total > history.data.items.length && <p className="mt-4 text-center text-xs text-slate-500">Showing the latest {history.data.items.length} of {history.data.total} messages.</p>}
      </PanelBody></Panel>
      <div className="flex flex-wrap gap-3 text-xs text-slate-500"><span className="inline-flex items-center gap-1.5"><Mail size={14}/>{customer.data.email}</span>{customer.data.phone && <span className="inline-flex items-center gap-1.5"><Phone size={14}/>{customer.data.phone}</span>}</div>
    </div>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>{label}</span>{children}{error && <span className="block text-xs font-normal text-red-600">{error}</span>}</label>;
}
