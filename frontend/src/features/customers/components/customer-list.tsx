"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Ellipsis, Mail, Pencil, Plus, Search, UserRound } from "lucide-react";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { Input } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui";
import { listCustomers } from "../api/customer-api";
import type { Customer } from "../types/customer.types";
import { CustomerFormDrawer } from "./customer-form-drawer";

export default function CustomersPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [drawerMode, setDrawerMode] = useState<"view" | "edit" | "create">("create");
  const params = useMemo(() => {
    const query = new URLSearchParams({ limit: "10", offset: String(page * 10) });
    if (search.trim()) query.set("search", search.trim());
    return query.toString();
  }, [page, search]);
  const customers = useQuery({ queryKey: ["customers", params], queryFn: () => listCustomers(params) });
  const pages = Math.max(1, Math.ceil((customers.data?.total ?? 0) / 10));

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Relationships" title="Customers" description="A shared view of the people your team supports." />
      <div className="flex justify-end">
        <Button onClick={() => { setEditingCustomer(null); setDrawerMode("create"); setDrawerOpen(true); }}><Plus size={16}/>Add customer</Button>
      </div>
      <Panel>
        <PanelHeader title="Customer directory" description={`${customers.data?.total ?? 0} customers in this view`}/>
        <PanelBody className="space-y-4">
          <div className="relative max-w-lg"><Search size={17} className="absolute left-3 top-3.5 text-slate-400"/><Input aria-label="Search customers" className="pl-10" placeholder="Search by name or email…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }}/></div>
          {customers.isError && <p role="alert" className="rounded-md border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">Unable to load customers. Try refreshing the page.</p>}
          {customers.isPending ? <div className="overflow-hidden rounded-lg border border-border"><Table aria-label="Loading customers"><TableHeader><TableRow>{["Customer", "Email", "Phone", "External reference", "Added", ""].map((heading, index) => <TableHead key={`${heading}-${index}`}>{heading}</TableHead>)}</TableRow></TableHeader><TableBody>{[1, 2, 3].map((row) => <TableRow key={row}>{[1, 2, 3, 4, 5, 6].map((cell) => <TableCell key={cell}><span className="block h-4 w-24 animate-pulse rounded bg-muted"/></TableCell>)}</TableRow>)}</TableBody></Table></div> : customers.data?.items.length ? <div className="overflow-hidden rounded-lg border border-border"><Table aria-label="Customer directory"><TableHeader><TableRow className="bg-muted/30 hover:bg-muted/30"><TableHead className="min-w-48">Customer</TableHead><TableHead>Email</TableHead><TableHead>Phone</TableHead><TableHead>External reference</TableHead><TableHead>Added</TableHead><TableHead className="w-12"><span className="sr-only">Actions</span></TableHead></TableRow></TableHeader><TableBody>{customers.data.items.map((customer) => <TableRow key={customer.id} tabIndex={0} aria-label={`View ${customer.name}`} onClick={() => { setEditingCustomer(customer); setDrawerMode("view"); setDrawerOpen(true); }} onKeyDown={(event) => { if ((event.key === "Enter" || event.key === " ") && event.target === event.currentTarget) { event.preventDefault(); setEditingCustomer(customer); setDrawerMode("view"); setDrawerOpen(true); } }} className="group cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring"><TableCell><div className="flex min-w-0 items-center gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary/8 text-primary"><UserRound size={16}/></span><span className="min-w-0 truncate font-medium text-foreground">{customer.name}</span></div></TableCell><TableCell className="max-w-64 text-muted-foreground"><span className="inline-flex min-w-0 items-center gap-2"><Mail size={14} className="shrink-0 text-muted-foreground/70"/><span className="truncate">{customer.email ?? "Email not provided"}</span></span></TableCell><TableCell className="text-muted-foreground">{customer.phone || <span aria-label="No phone provided">—</span>}</TableCell><TableCell className="text-muted-foreground">{customer.external_reference || "—"}</TableCell><TableCell className="text-muted-foreground">{formatDate(customer.created_at)}</TableCell><TableCell onClick={(event) => event.stopPropagation()}><DropdownMenu><DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${customer.name}`} title="Customer actions"/>}><Ellipsis size={16}/></DropdownMenuTrigger><DropdownMenuContent align="end" className="w-40"><DropdownMenuItem onClick={() => { setEditingCustomer(customer); setDrawerMode("edit"); setDrawerOpen(true); }}><Pencil size={14}/>Edit</DropdownMenuItem></DropdownMenuContent></DropdownMenu></TableCell></TableRow>)}</TableBody></Table></div> : <div className="rounded-lg border border-dashed border-border py-12 text-center"><UserRound size={28} className="mx-auto text-muted-foreground/50"/><h3 className="mt-3 text-sm font-semibold">No customers found</h3><p className="mt-1 text-sm text-muted-foreground">Add a customer or adjust your search.</p></div>}
          <div className="flex items-center justify-between border-t border-slate-100 pt-4"><p className="text-xs text-slate-500">Page {page + 1} of {pages}</p><div className="flex gap-2"><Button variant="secondary" size="sm" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}><ArrowLeft size={15}/> Previous</Button><Button variant="secondary" size="sm" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next <ArrowRight size={15}/></Button></div></div>
        </PanelBody>
      </Panel>
      <CustomerFormDrawer open={drawerOpen} onOpenChange={setDrawerOpen} customer={editingCustomer} mode={drawerMode} onModeChange={setDrawerMode} />
    </div>
  );
}
