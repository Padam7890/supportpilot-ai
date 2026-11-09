"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Mail, Monitor } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import {
  getNotificationPreferences,
  notificationKeys,
  updateNotificationPreference,
  type NotificationEventType,
} from "@/features/notifications/api/notifications-api";

const eventLabels: Record<NotificationEventType, { title: string; description: string }> = {
  "ticket.assigned": { title: "Tickets assigned to you", description: "When a teammate assigns a ticket to you." },
  "conversation.customer_replied": { title: "Customer replies", description: "When a customer sends a new message." },
  "ai.escalation_required": { title: "AI handoffs", description: "When the AI assistant needs a teammate to take over." },
};

export function NotificationPreferences() {
  const queryClient = useQueryClient();
  const preferences = useQuery({ queryKey: notificationKeys.preferences(), queryFn: getNotificationPreferences });
  const update = useMutation({
    mutationFn: ({ eventType, values }: { eventType: NotificationEventType; values: { in_app_enabled?: boolean; email_enabled?: boolean } }) => updateNotificationPreference(eventType, values),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: notificationKeys.all }); },
  });

  return <Panel>
    <PanelHeader title="Notification preferences" description="Choose how you want to hear about important workspace activity." action={<span className="grid size-9 place-items-center rounded-xl bg-muted text-muted-foreground"><Bell size={18}/></span>}/>
    <PanelBody>
      {preferences.isPending && <div role="status" className="space-y-3"><p className="text-sm text-muted-foreground">Loading notification preferences…</p><div className="h-16 animate-pulse rounded-lg bg-muted"/><div className="h-16 animate-pulse rounded-lg bg-muted"/></div>}
      {preferences.isError && <p role="alert" className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">Notification preferences could not be loaded. Refresh this page to try again.</p>}
      {update.isError && <p role="alert" className="mb-3 rounded-md bg-destructive/10 p-3 text-sm text-destructive">Your preference could not be saved. Please try again.</p>}
      {update.isSuccess && <p role="status" className="mb-3 text-sm text-muted-foreground">Preference saved.</p>}
      {!preferences.isPending && !preferences.isError && <div className="divide-y divide-border">
        <div className="grid grid-cols-[minmax(0,1fr)_5.5rem_5.5rem] items-center gap-3 pb-3 text-xs font-medium text-muted-foreground"><span>Event</span><span className="flex items-center gap-1"><Monitor size={13}/>In-app</span><span className="flex items-center gap-1"><Mail size={13}/>Email</span></div>
        {preferences.data?.map((item) => {
          const label = eventLabels[item.event_type];
          return <div key={item.event_type} className="grid grid-cols-[minmax(0,1fr)_5.5rem_5.5rem] items-center gap-3 py-4">
            <div className="min-w-0"><p className="text-sm font-medium text-foreground">{label.title}</p><p className="mt-1 text-xs text-muted-foreground">{label.description}</p></div>
            <Switch aria-label={`${label.title} in-app notifications`} checked={item.in_app_enabled} disabled={update.isPending} onCheckedChange={(checked) => update.mutate({ eventType: item.event_type, values: { in_app_enabled: checked } })}/>
            <Switch aria-label={`${label.title} email notifications`} checked={item.email_enabled} disabled={update.isPending} onCheckedChange={(checked) => update.mutate({ eventType: item.event_type, values: { email_enabled: checked } })}/>
          </div>;
        })}
      </div>}
      <p className="mt-4 border-t border-border pt-4 text-xs text-muted-foreground">Email notifications depend on your workspace email delivery configuration.</p>
    </PanelBody>
  </Panel>;
}
