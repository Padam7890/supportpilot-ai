"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { listCustomersForTicket } from "@/features/customers/api/customer-api";
import { listMembers } from "@/features/organization/api/organization-api";
import { listTeams, teamQueryKey } from "@/features/organization/api/team-api";
import { createTicket, updateTicket } from "../api/ticket-api";
import { createTicketSchema, updateTicketSchema } from "../schemas/ticket.schema";
import type { Ticket } from "../types/ticket.types";

type CreateValues = z.infer<typeof createTicketSchema>;
type UpdateValues = z.infer<typeof updateTicketSchema>;

type TicketFormDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ticket?: Ticket | null;
};

export function TicketFormDrawer({ open, onOpenChange, ticket = null }: TicketFormDrawerProps) {
  const queryClient = useQueryClient();
  const isEditing = Boolean(ticket);
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser, enabled: open });
  const canAssign = me.data?.role === "owner" || me.data?.role === "admin";
  const customers = useQuery({ queryKey: ["customers", "ticket-form"], queryFn: listCustomersForTicket, enabled: open && !isEditing });
  const teams = useQuery({ queryKey: teamQueryKey, queryFn: listTeams, enabled: open && canAssign });
  const members = useQuery({ queryKey: ["users"], queryFn: listMembers, enabled: open && canAssign });
  const createForm = useForm<CreateValues>({ resolver: zodResolver(createTicketSchema), defaultValues: { priority: "normal" } });
  const updateForm = useForm<UpdateValues>({ resolver: zodResolver(updateTicketSchema), defaultValues: {} });

  const create = useMutation({
    mutationFn: createTicket,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tickets"] }),
        queryClient.invalidateQueries({ queryKey: ["ticket-stats"] }),
      ]);
      createForm.reset({ priority: "normal" });
      onOpenChange(false);
    },
  });
  const update = useMutation({
    mutationFn: (values: UpdateValues) => updateTicket(ticket?.id ?? "", values),
    onSuccess: async (updated) => {
      queryClient.setQueryData(["ticket", updated.id], updated);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tickets"] }),
        queryClient.invalidateQueries({ queryKey: ["inbox"] }),
        queryClient.invalidateQueries({ queryKey: ["ticket-stats"] }),
      ]);
      onOpenChange(false);
    },
  });
  const resetCreateMutation = create.reset;
  const resetUpdateMutation = update.reset;

  useEffect(() => {
    if (!open) return;
    resetCreateMutation();
    resetUpdateMutation();
    createForm.reset({ priority: "normal" });
    updateForm.reset(ticket ? {
      status: ticket.status,
      priority: ticket.priority,
      team_id: ticket.team_id,
      assignee_id: ticket.assignee_id,
    } : {});
  }, [createForm, open, resetCreateMutation, resetUpdateMutation, ticket, updateForm]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent showCloseButton className="inset-y-0 right-0 left-auto top-0 flex h-dvh w-[min(560px,100vw)] max-w-none translate-x-0 translate-y-0 flex-col gap-0 rounded-none border-l border-r-0 p-0 duration-300 ease-out data-open:slide-in-from-right data-open:zoom-in-100 data-closed:slide-out-to-right data-closed:zoom-out-100 sm:max-w-none">
        <SheetHeader className="border-b border-border px-6 py-5 pr-14">
          <SheetTitle>{isEditing ? "Edit ticket" : "New ticket"}</SheetTitle>
          <SheetDescription>{isEditing ? "Update ticket status, priority, and routing." : "Create a support ticket for a customer."}</SheetDescription>
        </SheetHeader>
        {isEditing && ticket ? (
          <form className="flex min-h-0 flex-1 flex-col" onSubmit={updateForm.handleSubmit((values) => update.mutate(values))}>
            <div className="flex-1 space-y-5 overflow-y-auto px-6 py-6">
              <div className="rounded-lg border border-border bg-muted/30 p-4">
                <p className="text-xs font-medium text-muted-foreground">{ticket.customer_name ?? "Customer"} · #{ticket.id.slice(0, 8)}</p>
                <h3 className="mt-2 font-semibold text-foreground">{ticket.subject}</h3>
                {ticket.description && <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-sm text-muted-foreground">{ticket.description}</p>}
              </div>
              <FormField label="Status"><Select {...updateForm.register("status")}><option value="open">Open</option><option value="pending">Pending</option><option value="resolved">Resolved</option><option value="closed">Closed</option></Select></FormField>
              <FormField label="Priority"><Select {...updateForm.register("priority")}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></Select></FormField>
              {canAssign && <>
                <FormField label="Team"><Select {...updateForm.register("team_id", { setValueAs: (value) => value || null })}><option value="">No team</option>{teams.data?.filter((team) => team.is_active || team.id === ticket.team_id).map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</Select></FormField>
                <FormField label="Assignee"><Select {...updateForm.register("assignee_id", { setValueAs: (value) => value || null })}><option value="">Unassigned</option>{members.data?.filter((member) => member.is_active && ["owner", "admin", "agent"].includes(member.role)).map((member) => <option key={member.id} value={member.id}>{member.full_name} · {member.role}</option>)}</Select></FormField>
              </>}
              {update.isError && <ErrorMessage error={update.error} fallback="Ticket could not be updated." />}
            </div>
            <DrawerActions onCancel={() => onOpenChange(false)} pending={update.isPending} submitLabel="Save changes" />
          </form>
        ) : (
          <form className="flex min-h-0 flex-1 flex-col" onSubmit={createForm.handleSubmit((values) => create.mutate(values))}>
            <div className="flex-1 space-y-5 overflow-y-auto px-6 py-6">
              <FormField label="Customer" error={createForm.formState.errors.customer_id?.message}>
                <Select {...createForm.register("customer_id")}><option value="">Select customer</option>{customers.data?.items.map((customer) => <option key={customer.id} value={customer.id}>{customer.name} · {customer.email}</option>)}</Select>
              </FormField>
              <FormField label="Subject" error={createForm.formState.errors.subject?.message}><Input placeholder="What does the customer need help with?" {...createForm.register("subject")} /></FormField>
              <FormField label="Description"><Textarea placeholder="Add a few details to help your team get started." {...createForm.register("description")} /></FormField>
              <FormField label="Priority"><Select {...createForm.register("priority")}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></Select></FormField>
              {canAssign && <FormField label="Route to team"><Select {...createForm.register("team_id", { setValueAs: (value) => value || null })}><option value="">No team</option>{teams.data?.filter((team) => team.is_active).map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</Select></FormField>}
              {customers.data?.items.length === 0 && <p className="text-sm text-muted-foreground">Add a customer before creating a ticket.</p>}
              {create.isError && <ErrorMessage error={create.error} fallback="Ticket could not be created." />}
            </div>
            <DrawerActions onCancel={() => onOpenChange(false)} pending={create.isPending} submitLabel="Create ticket" disabled={(customers.data?.items.length ?? 0) === 0} />
          </form>
        )}
      </SheetContent>
    </Sheet>
  );
}

function FormField({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <label className="block space-y-2 text-sm font-medium text-foreground"><span>{label}</span>{children}{error && <span className="block text-xs font-normal text-destructive">{error}</span>}</label>;
}

function DrawerActions({ onCancel, pending, submitLabel, disabled = false }: { onCancel: () => void; pending: boolean; submitLabel: string; disabled?: boolean }) {
  return <div className="flex justify-end gap-2 border-t border-border bg-background px-6 py-4"><Button type="button" variant="outline" onClick={onCancel} disabled={pending}>Cancel</Button><Button type="submit" disabled={pending || disabled}>{pending ? "Saving…" : submitLabel}</Button></div>;
}

function ErrorMessage({ error, fallback }: { error: unknown; fallback: string }) {
  return <p role="alert" className="rounded-md border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">{error instanceof ApiError ? error.message : fallback}</p>;
}
