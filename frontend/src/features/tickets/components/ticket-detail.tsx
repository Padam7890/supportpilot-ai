"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, Link2, LoaderCircle, MessageSquare, Send, Unlink2, UserRound } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { createTicketLink, getTicket, listTicketLinks, removeTicketLink, searchTicketLinkCandidates, updateTicket } from "../api/ticket-api";
import { updateTicketSchema } from "../schemas/ticket.schema";
import { listConversations, listMessages, sendMessage as sendMessageRequest, startConversation as startConversationRequest } from "@/features/conversations/api/conversation-api";
import { sendMessageSchema } from "@/features/conversations/schemas/conversation.schema";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { getCustomer } from "@/features/customers/api/customer-api";
import { CustomerFormDrawer } from "@/features/customers/components/customer-form-drawer";
import type { Customer } from "@/features/customers/types/customer.types";
import { listMembers } from "@/features/organization/api/organization-api";
import { listTeams, teamQueryKey } from "@/features/organization/api/team-api";
import type { Ticket } from "../types/ticket.types";

export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState("");
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [linkSearch, setLinkSearch] = useState("");
  const [customerDrawerOpen, setCustomerDrawerOpen] = useState(false);
  const [customerDrawerMode, setCustomerDrawerMode] = useState<"view" | "edit">("view");
  const [customerDrawerLoading, setCustomerDrawerLoading] = useState(false);
  const [customerForDrawer, setCustomerForDrawer] = useState<Customer | null>(null);
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const ticketQuery = useQuery({ queryKey: ["ticket", id], queryFn: () => getTicket(id) });
  const conversations = useQuery({ queryKey: ["conversations", id], queryFn: () => listConversations(id) });
  const activeConversation = conversations.data?.length === 1
    ? conversations.data[0]
    : conversations.data?.find((conversation) => conversation.id === selectedConversationId);
  const messages = useQuery({
    queryKey: ["messages", activeConversation?.id],
    queryFn: () => listMessages(activeConversation!.id),
    enabled: Boolean(activeConversation),
  });
  const ticketLinks = useQuery({ queryKey: ["ticket-links", id], queryFn: () => listTicketLinks(id) });
  const members = useQuery({ queryKey: ["users"], queryFn: listMembers });
  const teams = useQuery({ queryKey: teamQueryKey, queryFn: listTeams });
  const form = useForm<z.infer<typeof sendMessageSchema>>({ resolver: zodResolver(sendMessageSchema) });
  const canWrite = ["owner", "admin", "agent"].includes(me.data?.role ?? "");
  const canAssign = ["owner", "admin"].includes(me.data?.role ?? "");
  const linkSearchTerm = linkSearch.trim();
  const linkSearchParams = new URLSearchParams({ search: linkSearchTerm, limit: "10", offset: "0" }).toString();
  const linkCandidates = useQuery({
    queryKey: ["ticket-link-candidates", id, linkSearchTerm],
    queryFn: () => searchTicketLinkCandidates(id, linkSearchParams),
    enabled: canWrite && linkSearchTerm.length >= 2,
  });
  const linkedTicketIds = new Set(ticketLinks.data?.items.map((link) => link.related_ticket_id) ?? []);
  const linkCandidateItems = linkCandidates.data?.items.filter(
    (candidate) => candidate.id !== id && !linkedTicketIds.has(candidate.id),
  ) ?? [];

  const update = useMutation({
    mutationFn: (changes: z.infer<typeof updateTicketSchema>) => updateTicket(id, changes),
    onSuccess: async () => { setFeedback("Ticket updated."); await Promise.all([queryClient.invalidateQueries({ queryKey: ["ticket", id] }), queryClient.invalidateQueries({ queryKey: ["tickets"] }), queryClient.invalidateQueries({ queryKey: ["ticket-activity", id] }), queryClient.invalidateQueries({ queryKey: ["ticket-stats"] })]); },
    onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Ticket could not be updated."),
  });
  const startConversation = useMutation({
    mutationFn: () => startConversationRequest(id),
    onSuccess: async (conversation) => { setSelectedConversationId(conversation.id); setFeedback("Conversation started."); await queryClient.invalidateQueries({ queryKey: ["conversations", id] }); },
    onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Could not start a conversation."),
  });

  const sendMessage = useMutation({
    mutationFn: (values: z.infer<typeof sendMessageSchema>) => sendMessageRequest(activeConversation!.id, values),
    onSuccess: async () => { form.reset(); await queryClient.invalidateQueries({ queryKey: ["messages", activeConversation?.id] }); },
    onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Message could not be sent."),
  });

  const createLink = useMutation({
    mutationFn: (relatedTicketId: string) => createTicketLink(id, relatedTicketId),
    onSuccess: async () => {
      setLinkSearch("");
      setFeedback("Related ticket linked.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["ticket-links", id] }),
        queryClient.invalidateQueries({ queryKey: ["ticket-link-candidates", id] }),
        queryClient.invalidateQueries({ queryKey: ["ticket-activity"] }),
      ]);
    },
    onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Could not link the tickets."),
  });

  const removeLink = useMutation({
    mutationFn: (linkId: string) => removeTicketLink(id, linkId),
    onSuccess: async () => {
      setFeedback("Ticket link removed.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["ticket-links", id] }),
        queryClient.invalidateQueries({ queryKey: ["ticket-link-candidates", id] }),
        queryClient.invalidateQueries({ queryKey: ["ticket-activity"] }),
      ]);
    },
    onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Could not remove the ticket link."),
  });

  if (ticketQuery.isPending) return <div className="h-64 animate-pulse rounded-2xl bg-white"/>;
  if (ticketQuery.isError || !ticketQuery.data) return <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">Ticket not found or unavailable. <Link href="/dashboard/tickets" className="font-semibold underline">Back to tickets</Link></div>;
  const ticket = ticketQuery.data;

  async function openCustomerDetails() {
    setCustomerDrawerLoading(true);
    setFeedback("");
    try {
      const customer = await queryClient.fetchQuery({
        queryKey: ["customer", ticket.customer_id],
        queryFn: () => getCustomer(ticket.customer_id),
      });
      setCustomerForDrawer(customer);
      setCustomerDrawerMode("view");
      setCustomerDrawerOpen(true);
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : "Customer details could not be loaded.");
    } finally {
      setCustomerDrawerLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <Link href="/dashboard/tickets" className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900"><ArrowLeft size={16}/> Ticket queue</Link>
      <div className="flex flex-wrap items-start justify-between gap-4"><div className="max-w-3xl"><p className="text-sm font-semibold text-blue-700">Ticket #{id.slice(0, 8)}</p><h1 className="mt-1 text-3xl font-bold tracking-tight">{ticket.subject}</h1><p className="mt-2 text-sm text-slate-500">{ticket.customer_name ?? "Customer"} · created {formatDateTime(ticket.created_at)}</p></div><div className="flex flex-wrap gap-2"><Select aria-label="Ticket status" value={ticket.status} disabled={!canWrite || update.isPending} onChange={(event) => update.mutate({ status: event.target.value as Ticket["status"] })}><option value="open">Open</option><option value="pending">Pending</option><option value="resolved">Resolved</option><option value="closed">Closed</option></Select><Select aria-label="Ticket priority" value={ticket.priority} disabled={!canWrite || update.isPending} onChange={(event) => update.mutate({ priority: event.target.value as Ticket["priority"] })}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></Select></div></div>
      {feedback && <p role="status" className="rounded-xl bg-blue-50 px-4 py-3 text-sm text-blue-800">{feedback}</p>}
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,0.75fr)]">
        <div className="space-y-5">
          <Panel><PanelHeader title="Conversation" description="Messages exchanged about this support request" action={activeConversation ? <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">Active</span> : undefined}/><PanelBody>
            {!activeConversation && conversations.data?.length === 0 ? <div className="py-8 text-center"><MessageSquare size={27} className="mx-auto text-slate-300"/><p className="mt-3 font-semibold">No conversation yet</p><p className="mt-1 text-sm text-slate-500">Start the thread to begin replying to this customer.</p>{canWrite && <Button className="mt-4" onClick={() => startConversation.mutate()} disabled={startConversation.isPending}>{startConversation.isPending ? "Starting…" : "Start conversation"}</Button>}</div> : null}
            {!activeConversation && (conversations.data?.length ?? 0) > 1 && <div className="py-6"><p className="font-semibold">Choose a conversation</p><p className="mt-1 text-sm text-slate-500">Each conversation has its own message history.</p><div className="mt-4 space-y-2">{conversations.data?.map((conversation, index) => <Button variant="unstyled" key={conversation.id} type="button" onClick={() => setSelectedConversationId(conversation.id)} className="flex w-full items-center justify-between rounded-xl border border-slate-200 p-3 text-left hover:border-blue-300 hover:bg-blue-50"><span><span className="block text-sm font-semibold">Conversation {conversations.data.length - index}</span><span className="text-xs text-slate-500">{conversation.channel} · {formatDateTime(conversation.updated_at)}</span></span><span className="text-blue-700">Open →</span></Button>)}</div></div>}
            {activeConversation && <>
              <div className="max-h-[440px] space-y-4 overflow-y-auto pr-1">
                {messages.isPending && <div className="h-28 animate-pulse rounded-xl bg-slate-100"/>}
                {messages.data?.map((message) => <div key={message.id} className={`flex ${message.sender_type === "agent" ? "justify-end" : "justify-start"}`}><div className={`max-w-[85%] rounded-2xl px-4 py-3 ${message.sender_type === "agent" ? "rounded-br-md bg-blue-700 text-white" : "rounded-bl-md bg-slate-100 text-slate-900"}`}><div className={`mb-1.5 flex items-center gap-2 text-xs ${message.sender_type === "agent" ? "text-blue-100" : "text-slate-500"}`}><span className="font-semibold">{message.sender_name ?? message.sender_type}</span><span>·</span><time>{formatDateTime(message.created_at)}</time></div><p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p></div></div>)}
                {messages.data?.length === 0 && <p className="py-8 text-center text-sm text-slate-500">No messages yet. Send the first reply.</p>}
                {messages.isError && <p role="alert" className="text-sm text-red-700">Unable to load messages.</p>}
              </div>
              {canWrite && <form className="mt-5 border-t border-slate-100 pt-4" onSubmit={form.handleSubmit((values) => sendMessage.mutate(values))}><label htmlFor="message-content" className="sr-only">Write a message</label><Textarea id="message-content" placeholder="Write a reply…" {...form.register("content")}/>{form.formState.errors.content && <p className="mt-1 text-xs text-red-600">{form.formState.errors.content.message}</p>}<div className="mt-3 flex justify-end"><Button type="submit" disabled={sendMessage.isPending}>{sendMessage.isPending ? "Sending…" : <>Send reply <Send size={15}/></>}</Button></div></form>}
            </>}
          </PanelBody></Panel>
          <Panel><PanelHeader title="Description" description="The customer’s original request"/><PanelBody><p className="whitespace-pre-wrap text-sm leading-7 text-slate-700">{ticket.description || "No description provided."}</p></PanelBody></Panel>
        </div>
        <div className="space-y-5">
          <Panel><PanelHeader title="Ticket details"/><PanelBody className="space-y-4"><Info label="Customer" value={ticket.customer_name ?? "Customer"}/><Info label="Created" value={formatDateTime(ticket.created_at)}/><Info label="Last updated" value={formatDateTime(ticket.updated_at)}/>
            <div><label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="team">Team</label><Select id="team" value={ticket.team_id ?? ""} disabled={!canAssign || update.isPending || teams.isPending} onChange={(event) => update.mutate({ team_id: event.target.value || null, assignee_id: null })}><option value="">No team</option>{teams.data?.filter((team) => team.is_active || team.id === ticket.team_id).map((team) => <option key={team.id} value={team.id} disabled={!team.is_active}>{team.name}{team.is_active ? "" : " · inactive"}</option>)}</Select>{canAssign && ticket.assignee_id && <p className="mt-1 text-xs text-slate-500">Changing the team clears the current assignee.</p>}{!canAssign && <p className="mt-1 text-xs text-slate-400">Only Owners and Admins can route tickets to teams.</p>}</div>
            <div><label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="assignee">Assignee</label><Select id="assignee" value={ticket.assignee_id ?? ""} disabled={!canAssign || update.isPending} onChange={(event) => update.mutate({ assignee_id: event.target.value || null })}><option value="">Unassigned</option>{members.data?.filter((member) => member.is_active && ["owner", "admin", "agent"].includes(member.role) && (!ticket.team_id || teams.data?.find((team) => team.id === ticket.team_id)?.members.some((teamMember) => teamMember.id === member.id))).map((member) => <option key={member.id} value={member.id}>{member.full_name} · {member.role}</option>)}</Select></div>
          </PanelBody></Panel>
          <Panel><PanelHeader title="Related tickets" description="Link similar or follow-up requests without merging their histories" action={<Link2 size={16} className="text-blue-700"/>}/><PanelBody className="space-y-4">
            {ticketLinks.isPending ? <div role="status" className="h-14 animate-pulse rounded-xl bg-slate-100"/> : ticketLinks.isError ? <p role="alert" className="text-sm text-red-700">Related tickets could not be loaded.</p> : ticketLinks.data?.items.length ? <div className="space-y-2">{ticketLinks.data.items.map((related) => <div key={related.id} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3"><Link href={`/dashboard/tickets/${related.related_ticket_id}`} className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-blue-700 hover:underline">{related.related_ticket_subject}</span><span className="mt-1 block text-xs capitalize text-slate-500">{related.related_ticket_status} · {related.related_ticket_priority}</span></Link>{canWrite && <Button variant="unstyled" type="button" aria-label={`Unlink ${related.related_ticket_subject}`} title="Remove link" disabled={removeLink.isPending} onClick={() => removeLink.mutate(related.id)} className="grid size-8 shrink-0 place-items-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-red-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"><Unlink2 size={15}/></Button>}</div>)}</div> : <p className="text-sm text-slate-500">No related tickets yet.</p>}
            {canWrite && <div className="space-y-2 border-t border-slate-100 pt-4"><label htmlFor="related-ticket-search" className="block text-xs font-semibold text-slate-600">Find a ticket to link</label><Input id="related-ticket-search" value={linkSearch} onChange={(event) => setLinkSearch(event.target.value)} placeholder="Search ticket subject or customer"/><p className="text-xs text-slate-500">Search at least two characters. Ticket conversations remain separate.</p>{linkSearchTerm.length >= 2 && linkCandidates.isPending && <p role="status" className="text-xs text-slate-500">Searching tickets…</p>}{linkSearchTerm.length >= 2 && linkCandidates.isError && <p role="alert" className="text-xs text-red-700">Ticket search failed.</p>}{linkSearchTerm.length >= 2 && linkCandidates.data && (linkCandidateItems.length ? <div className="space-y-1">{linkCandidateItems.map((candidate) => <Button variant="unstyled" type="button" key={candidate.id} onClick={() => createLink.mutate(candidate.id)} disabled={createLink.isPending} className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left hover:bg-blue-50 disabled:opacity-60"><span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold text-slate-800">{candidate.subject}</span><span className="mt-0.5 block truncate text-[11px] text-slate-500">{candidate.customer_name ?? "Customer"} · {candidate.status}</span></span><Link2 size={14} className="shrink-0 text-blue-700"/></Button>)}</div> : <p className="text-xs text-slate-500">No other matching tickets found.</p>)}{createLink.isPending && <p role="status" className="text-xs text-blue-700">Linking tickets…</p>}</div>}
          </PanelBody></Panel>
          <Panel><PanelHeader title="Customer"/><PanelBody><Button type="button" variant="unstyled" disabled={customerDrawerLoading} onClick={openCustomerDetails} className="flex w-full items-center gap-3 rounded-lg text-left hover:bg-muted/40"><span className="grid size-10 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground">{customerDrawerLoading ? <LoaderCircle size={17} className="animate-spin"/> : <UserRound size={18}/>}</span><span className="min-w-0 truncate font-medium text-foreground">{ticket.customer_name ?? "View customer"}</span><span className="ml-auto text-xs text-primary">{customerDrawerLoading ? "Loading…" : "View profile"}</span></Button></PanelBody></Panel>
        </div>
      </div>
      {customerForDrawer && <CustomerFormDrawer open={customerDrawerOpen} onOpenChange={setCustomerDrawerOpen} customer={customerForDrawer} mode={customerDrawerMode} onModeChange={(mode) => { if (mode !== "create") setCustomerDrawerMode(mode); }}/>}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p><p className="mt-1.5 text-sm font-medium text-slate-800">{value}</p></div>;
}
