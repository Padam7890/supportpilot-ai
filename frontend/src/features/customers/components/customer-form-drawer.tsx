"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowUpRight, Mail, Pencil, Phone, Ticket as TicketIcon } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { createCustomer, listCustomerTickets, updateCustomer } from "../api/customer-api";
import type { Customer } from "../types/customer.types";
import { updateCustomerSchema } from "../schemas/customer.schema";

const customerFormSchema = updateCustomerSchema;
type CustomerFormValues = z.infer<typeof customerFormSchema>;

type CustomerFormDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customer?: Customer | null;
  mode: "view" | "edit" | "create";
  onModeChange?: (mode: "view" | "edit" | "create") => void;
};

export function CustomerFormDrawer({ open, onOpenChange, customer = null, mode, onModeChange }: CustomerFormDrawerProps) {
  const queryClient = useQueryClient();
  const tickets = useQuery({
    queryKey: ["customer-tickets", customer?.id],
    queryFn: () => listCustomerTickets(customer?.id ?? ""),
    enabled: Boolean(open && mode === "view" && customer),
  });
  const form = useForm<CustomerFormValues>({
    resolver: zodResolver(customerFormSchema),
    defaultValues: { name: "", email: "", phone: "", external_reference: "" },
  });
  const resetForm = form.reset;
  const save = useMutation({
    mutationFn: (values: CustomerFormValues) => customer
      ? updateCustomer(customer.id, values)
      : createCustomer(values),
    onSuccess: async (saved) => {
      if (customer) queryClient.setQueryData(["customer", customer.id], saved);
      await queryClient.invalidateQueries({ queryKey: ["customers"] });
      onOpenChange(false);
    },
  });
  const resetSave = save.reset;

  useEffect(() => {
    if (!open || mode === "view") return;
    resetSave();
    resetForm({
      name: customer?.name ?? "",
      email: customer?.email ?? "",
      phone: customer?.phone ?? "",
      external_reference: customer?.external_reference ?? "",
    });
  }, [customer, mode, open, resetForm, resetSave]);

  const isEditing = mode === "edit";
  const viewCustomer = mode === "view" ? customer : null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent showCloseButton className="inset-y-0 right-0 left-auto top-0 flex h-dvh w-[min(760px,100vw)] max-w-none translate-x-0 translate-y-0 flex-col gap-0 rounded-none border-l border-r-0 p-0 duration-300 ease-out data-open:slide-in-from-right data-open:zoom-in-100 data-closed:slide-out-to-right data-closed:zoom-out-100 sm:max-w-none">
        <SheetHeader className="border-b border-border px-6 py-5 pr-14">
          <SheetTitle>{mode === "view" ? customer?.name ?? "Customer" : isEditing ? "Edit customer" : "Add customer"}</SheetTitle>
          <SheetDescription>
            {mode === "view" ? "Customer profile and contact information." : isEditing ? "Update this customer’s contact information." : "Create a customer record for your support team."}
          </SheetDescription>
        </SheetHeader>
        {viewCustomer ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex-1 space-y-7 overflow-y-auto px-6 py-6 sm:px-8">
              <section className="flex items-center gap-4 rounded-lg border border-border bg-muted/20 p-4">
                <div className="grid size-12 shrink-0 place-items-center rounded-full bg-primary/10 text-lg font-semibold text-primary">{viewCustomer.name.slice(0, 1).toUpperCase()}</div>
                <div className="min-w-0 flex-1"><h3 className="truncate font-semibold text-foreground">{viewCustomer.name}</h3><p className="mt-1 text-sm text-muted-foreground">Customer since {formatDate(viewCustomer.created_at)}</p></div>
                <Button type="button" variant="ghost" size="icon" aria-label="Edit customer" title="Edit customer" onClick={() => onModeChange?.("edit")}><Pencil size={16}/></Button>
              </section>
              <section className="space-y-4">
                <div><h3 className="text-sm font-semibold text-foreground">Customer details</h3><p className="mt-1 text-xs text-muted-foreground">Contact information and merchant reference.</p></div>
                <div className="grid gap-x-8 gap-y-5 rounded-lg border border-border p-5 sm:grid-cols-2">
                <ReadOnlyField label="Full name" value={viewCustomer.name} />
                <ReadOnlyField label="Email" value={viewCustomer.email} icon={<Mail size={15} />} />
                <ReadOnlyField label="Phone" value={viewCustomer.phone} icon={<Phone size={15} />} />
                <ReadOnlyField label="External reference" value={viewCustomer.external_reference} />
                </div>
              </section>
              <section className="space-y-4">
                <div className="flex items-end justify-between gap-3"><div><h3 className="text-sm font-semibold text-foreground">Customer tickets</h3><p className="mt-1 text-xs text-muted-foreground">Support history for this customer.</p></div>{tickets.data && <span className="text-xs text-muted-foreground">{tickets.data.total} total</span>}</div>
                {tickets.isPending ? <div className="space-y-2" aria-label="Loading customer tickets">{[1, 2, 3].map((item) => <div key={item} className="h-16 animate-pulse rounded-md bg-muted" />)}</div> : tickets.isError ? <p role="alert" className="rounded-md border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">Could not load this customer’s tickets.</p> : tickets.data.items.length ? <div className="overflow-hidden rounded-lg border border-border">{tickets.data.items.map((ticket) => <Link key={ticket.id} href={`/dashboard/tickets/${ticket.id}`} className="flex items-center gap-3 border-b border-border p-4 last:border-b-0 hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-ring"><span className="grid size-9 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground"><TicketIcon size={16}/></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-foreground">{ticket.subject}</span><span className="mt-1 block text-xs capitalize text-muted-foreground">{ticket.status} · {ticket.priority} priority · {formatDate(ticket.created_at)}</span></span><ArrowUpRight size={15} className="shrink-0 text-muted-foreground"/></Link>)}</div> : <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center"><TicketIcon size={20} className="mx-auto text-muted-foreground/60"/><p className="mt-2 text-sm font-medium text-foreground">No tickets yet</p><p className="mt-1 text-xs text-muted-foreground">Tickets from this customer will appear here.</p></div>}
              </section>
            </div>
          </div>
        ) : (
        <form className="flex min-h-0 flex-1 flex-col" onSubmit={form.handleSubmit((values) => save.mutate(values))}>
          <div className="flex-1 space-y-5 overflow-y-auto px-6 py-6">
            <FormField label="Full name" error={form.formState.errors.name?.message}>
              <Input autoComplete="name" autoFocus {...form.register("name")} />
            </FormField>
            <FormField label="Email" error={form.formState.errors.email?.message}>
              <Input type="email" autoComplete="email" {...form.register("email")} />
            </FormField>
            <FormField label="Phone" error={form.formState.errors.phone?.message}>
              <Input type="tel" autoComplete="tel" {...form.register("phone")} />
            </FormField>
            <FormField label="External reference" error={form.formState.errors.external_reference?.message}>
              <Input placeholder="Optional CRM ID" {...form.register("external_reference")} />
            </FormField>
            {save.isError && (
              <p role="alert" className="rounded-md border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">
              {save.error instanceof ApiError ? save.error.message : `Customer could not be ${isEditing ? "updated" : "created"}.`}
              </p>
            )}
          </div>
          <div className="flex justify-end gap-2 border-t border-border bg-background px-6 py-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={save.isPending}>Cancel</Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : isEditing ? "Save changes" : "Create customer"}
            </Button>
          </div>
        </form>
        )}
      </SheetContent>
    </Sheet>
  );
}

function ReadOnlyField({ label, value, icon }: { label: string; value: string | null; icon?: React.ReactNode }) {
  return <div className="space-y-1.5"><p className="text-xs font-medium text-muted-foreground">{label}</p><p className="flex items-center gap-2 text-sm text-foreground">{icon && <span className="text-muted-foreground">{icon}</span>}{value || "—"}</p></div>;
}

function FormField({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-2 text-sm font-medium text-foreground">
      <span>{label}</span>
      {children}
      {error && <span className="block text-xs font-normal text-destructive">{error}</span>}
    </label>
  );
}
