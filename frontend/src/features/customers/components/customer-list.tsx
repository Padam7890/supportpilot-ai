"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { ArrowLeft, ArrowRight, Mail, Plus, Search, UserRound } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { createCustomer, listCustomers } from "../api/customer-api";
import { createCustomerSchema } from "../schemas/customer.schema";

export default function CustomersPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const queryClient = useQueryClient();
  const params = useMemo(() => {
    const query = new URLSearchParams({ limit: "10", offset: String(page * 10) });
    if (search.trim()) query.set("search", search.trim());
    return query.toString();
  }, [page, search]);
  const customers = useQuery({ queryKey: ["customers", params], queryFn: () => listCustomers(params) });
  const form = useForm<z.infer<typeof createCustomerSchema>>({ resolver: zodResolver(createCustomerSchema) });
  const create = useMutation({
    mutationFn: createCustomer,
    onSuccess: async () => { form.reset(); await queryClient.invalidateQueries({ queryKey: ["customers"] }); },
  });
  const pages = Math.max(1, Math.ceil((customers.data?.total ?? 0) / 10));

  return (
    <div className="space-y-6">
      <div><p className="text-sm font-semibold text-blue-700">Relationships</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Customers</h1><p className="mt-2 text-sm text-slate-500">A shared view of the people your team supports.</p></div>
      <details className="group rounded-2xl border border-blue-100 bg-blue-50/70 open:bg-white open:shadow-sm">
        <summary className="flex cursor-pointer list-none items-center gap-3 p-4 text-sm font-semibold text-blue-800"><span className="grid size-9 place-items-center rounded-xl bg-white"><Plus size={17}/></span>Add a customer<span className="ml-auto text-xs font-medium text-blue-600 group-open:hidden">Open form</span></summary>
        <form className="grid gap-4 border-t border-slate-100 p-5 md:grid-cols-2" onSubmit={form.handleSubmit((values) => create.mutate(values))}>
          <Field label="Full name" error={form.formState.errors.name?.message}><Input autoComplete="name" {...form.register("name")}/></Field>
          <Field label="Email" error={form.formState.errors.email?.message}><Input type="email" autoComplete="email" {...form.register("email")}/></Field>
          <Field label="Phone" error={form.formState.errors.phone?.message}><Input type="tel" autoComplete="tel" {...form.register("phone")}/></Field>
          <Field label="External reference" error={form.formState.errors.external_reference?.message}><Input placeholder="Optional CRM ID" {...form.register("external_reference")}/></Field>
          {create.isError && <p role="alert" className="text-sm text-red-700 md:col-span-2">{create.error instanceof ApiError ? create.error.message : "Customer could not be created."}</p>}
          <div className="md:col-span-2"><Button type="submit" disabled={create.isPending}>{create.isPending ? "Saving…" : "Save customer"}</Button></div>
        </form>
      </details>
      <Panel>
        <PanelHeader title="Customer directory" description={`${customers.data?.total ?? 0} customers in this view`}/>
        <PanelBody className="space-y-4">
          <div className="relative max-w-lg"><Search size={17} className="absolute left-3 top-3.5 text-slate-400"/><Input aria-label="Search customers" className="pl-10" placeholder="Search by name or email…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }}/></div>
          {customers.isError && <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">Unable to load customers.</div>}
          {customers.isPending ? <div className="space-y-3">{[1,2,3].map((row) => <div className="h-16 animate-pulse rounded-xl bg-slate-100" key={row}/>)}</div> : customers.data?.items.length ? <div className="divide-y divide-slate-100">{customers.data.items.map((customer) => <Link href={`/dashboard/customers/${customer.id}`} key={customer.id} className="flex flex-wrap items-center gap-3 rounded-xl px-3 py-4 hover:bg-slate-50 sm:gap-4"><span className="grid size-11 shrink-0 place-items-center rounded-full bg-blue-50 text-blue-700"><UserRound size={19}/></span><span className="min-w-40 flex-1"><span className="block font-semibold text-slate-900">{customer.name}</span><span className="mt-1 flex items-center gap-1.5 text-xs text-slate-500"><Mail size={13}/>{customer.email}</span></span><span className="text-xs text-slate-500">Added {formatDate(customer.created_at)}</span><span className="text-sm font-semibold text-blue-700">View →</span></Link>)}</div> : <div className="rounded-2xl border border-dashed border-slate-200 py-14 text-center"><UserRound size={30} className="mx-auto text-slate-300"/><h3 className="mt-3 font-semibold">No customers found</h3><p className="mt-1 text-sm text-slate-500">Add a customer to keep their support history in one place.</p></div>}
          <div className="flex items-center justify-between border-t border-slate-100 pt-4"><p className="text-xs text-slate-500">Page {page + 1} of {pages}</p><div className="flex gap-2"><Button variant="secondary" size="sm" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}><ArrowLeft size={15}/> Previous</Button><Button variant="secondary" size="sm" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next <ArrowRight size={15}/></Button></div></div>
        </PanelBody>
      </Panel>
    </div>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>{label}</span>{children}{error && <span className="block text-xs font-normal text-red-600">{error}</span>}</label>;
}
