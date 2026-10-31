"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, MessageSquare, Send, Sparkles, UserRound } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { getTicket, getTicketActivity, updateTicket } from "../api/ticket-api";
import { updateTicketSchema } from "../schemas/ticket.schema";
import { listConversations, listMessages, sendMessage as sendMessageRequest, startConversation as startConversationRequest } from "@/features/conversations/api/conversation-api";
import { sendMessageSchema } from "@/features/conversations/schemas/conversation.schema";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { listMembers } from "@/features/organization/api/organization-api";
import type { Ticket, TicketActivity } from "../types/ticket.types";

export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState("");
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const ticketQuery = useQuery({ queryKey: ["ticket", id], queryFn: () => getTicket(id) });
  const conversations = useQuery({ queryKey: ["conversations", id], queryFn: () => listConversations(id) });
  const activeConversation = conversations.data?.[0];
  const messages = useQuery({
    queryKey: ["messages", activeConversation?.id],
    queryFn: () => listMessages(activeConversation!.id),
    enabled: Boolean(activeConversation),
  });
  const activity = useQuery({ queryKey: ["ticket-activity", id], queryFn: () => getTicketActivity(id) });
  const members = useQuery({ queryKey: ["users"], queryFn: listMembers });
  const form = useForm<z.infer<typeof sendMessageSchema>>({ resolver: zodResolver(sendMessageSchema) });
  const canWrite = ["owner", "admin", "agent"].includes(me.data?.role ?? "");
  const canAssign = ["owner", "admin"].includes(me.data?.role ?? "");

  const update = useMutation({
    mutationFn: (changes: z.infer<typeof updateTicketSchema>) => updateTicket(id, changes),
    onSuccess: async () => { setFeedback("Ticket updated."); await Promise.all([queryClient.invalidateQueries({ queryKey: ["ticket", id] }), queryClient.invalidateQueries({ queryKey: ["tickets"] }), queryClient.invalidateQueries({ queryKey: ["ticket-activity", id] }), queryClient.invalidateQueries({ queryKey: ["ticket-stats"] })]); },
    onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Ticket could not be updated."),
  });
  const startConversation = useMutation({
    mutationFn: () => startConversationRequest(id),
    onSuccess: async () => { setFeedback("Conversation started."); await queryClient.invalidateQueries({ queryKey: ["conversations", id] }); },
    onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Could not start a conversation."),
  });
  const sendMessage = useMutation({
    mutationFn: (values: z.infer<typeof sendMessageSchema>) => sendMessageRequest(activeConversation!.id, values),
    onSuccess: async () => { form.reset(); await queryClient.invalidateQueries({ queryKey: ["messages", activeConversation?.id] }); },
    onError: (error) => setFeedback(error instanceof ApiError ? error.message : "Message could not be sent."),
  });

  if (ticketQuery.isPending) return <div className="h-64 animate-pulse rounded-2xl bg-white"/>;
  if (ticketQuery.isError || !ticketQuery.data) return <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">Ticket not found or unavailable. <Link href="/dashboard/tickets" className="font-semibold underline">Back to tickets</Link></div>;
  const ticket = ticketQuery.data;

  return (
    <div className="space-y-6">
      <Link href="/dashboard/tickets" className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900"><ArrowLeft size={16}/> Ticket queue</Link>
      <div className="flex flex-wrap items-start justify-between gap-4"><div className="max-w-3xl"><p className="text-sm font-semibold text-blue-700">Ticket #{id.slice(0, 8)}</p><h1 className="mt-1 text-3xl font-bold tracking-tight">{ticket.subject}</h1><p className="mt-2 text-sm text-slate-500">{ticket.customer_name ?? "Customer"} · created {formatDateTime(ticket.created_at)}</p></div><div className="flex flex-wrap gap-2"><Select aria-label="Ticket status" value={ticket.status} disabled={!canWrite || update.isPending} onChange={(event) => update.mutate({ status: event.target.value as Ticket["status"] })}><option value="open">Open</option><option value="pending">Pending</option><option value="resolved">Resolved</option><option value="closed">Closed</option></Select><Select aria-label="Ticket priority" value={ticket.priority} disabled={!canWrite || update.isPending} onChange={(event) => update.mutate({ priority: event.target.value as Ticket["priority"] })}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></Select></div></div>
      {feedback && <p role="status" className="rounded-xl bg-blue-50 px-4 py-3 text-sm text-blue-800">{feedback}</p>}
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,0.75fr)]">
        <div className="space-y-5">
          <Panel><PanelHeader title="Conversation" description="Messages exchanged about this support request" action={activeConversation ? <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">Active</span> : undefined}/><PanelBody>
            {!activeConversation ? <div className="py-8 text-center"><MessageSquare size={27} className="mx-auto text-slate-300"/><p className="mt-3 font-semibold">No conversation yet</p><p className="mt-1 text-sm text-slate-500">Start the thread to begin replying to this customer.</p>{canWrite && <Button className="mt-4" onClick={() => startConversation.mutate()} disabled={startConversation.isPending}>{startConversation.isPending ? "Starting…" : "Start conversation"}</Button>}</div> : <>
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
          <Panel><PanelHeader title="Ticket details"/><PanelBody className="space-y-4"><Info label="Customer" value={ticket.customer_name ?? "Customer"}/><Info label="Created" value={formatDateTime(ticket.created_at)}/><Info label="Last updated" value={formatDateTime(ticket.updated_at)}/><div><label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-400" htmlFor="assignee">Assignee</label><Select id="assignee" value={ticket.assignee_id ?? ""} disabled={!canAssign || update.isPending} onChange={(event) => update.mutate({ assignee_id: event.target.value || null })}><option value="">Unassigned</option>{members.data?.filter((member) => member.is_active && ["admin", "agent"].includes(member.role)).map((member) => <option key={member.id} value={member.id}>{member.full_name} · {member.role}</option>)}</Select>{!canAssign && <p className="mt-1 text-xs text-slate-400">Only owners and admins can assign tickets.</p>}</div></PanelBody></Panel>
          <Panel><PanelHeader title="Activity" description="Ticket changes and ownership"/><PanelBody className="space-y-4">{activity.isPending ? <div className="h-28 animate-pulse rounded-xl bg-slate-100"/> : activity.isError ? <p className="text-sm text-red-700">Unable to load activity.</p> : activity.data?.length ? activity.data.map((entry) => <div key={entry.id} className="flex gap-3"><span className="mt-1 grid size-8 shrink-0 place-items-center rounded-full bg-blue-50 text-blue-700"><Sparkles size={14}/></span><div><p className="text-sm font-medium text-slate-800">{activityLabel(entry.activity_type, entry.details)}</p><p className="mt-1 text-xs text-slate-500">{entry.actor_name ?? "System"} · {formatDateTime(entry.created_at)}</p></div></div>) : <p className="text-sm text-slate-500">No activity recorded.</p>}</PanelBody></Panel>
          <Panel><PanelHeader title="Customer"/><PanelBody><Link href={`/dashboard/customers/${ticket.customer_id}`} className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-full bg-slate-100 text-slate-500"><UserRound size={18}/></span><span className="font-semibold text-blue-700 hover:underline">{ticket.customer_name ?? "View customer"}</span></Link></PanelBody></Panel>
        </div>
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p><p className="mt-1.5 text-sm font-medium text-slate-800">{value}</p></div>;
}

function activityLabel(type: string, details: TicketActivity["details"]) {
  if (type === "created") return "Ticket created";
  const changes = Object.keys(details).map((key) => key.replaceAll("_", " ")).join(", ");
  return changes ? `Updated ${changes}` : "Ticket updated";
}
