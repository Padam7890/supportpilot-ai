"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Check, CheckCheck, Inbox, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import {
  dismissNotification,
  getNotifications,
  getUnreadNotificationCount,
  markAllNotificationsRead,
  markNotificationRead,
  notificationKeys,
  type NotificationItem,
} from "@/features/notifications/api/notifications-api";

function internalHref(item: NotificationItem) {
  const href = item.action_url;
  return href && href.startsWith("/dashboard/") && !href.startsWith("//") && !href.includes("\\") ? href : "/dashboard/inbox";
}

function relativeTime(value: string) {
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime());
  if (elapsed < 60_000) return "Just now";
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)}m ago`;
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)}h ago`;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(value));
}

export function NotificationPopover() {
  const [open, setOpen] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const queryClient = useQueryClient();
  const unread = useQuery({ queryKey: notificationKeys.unread(), queryFn: getUnreadNotificationCount, refetchInterval: 45_000, refetchIntervalInBackground: false });
  const page = useInfiniteQuery({
    queryKey: notificationKeys.list(unreadOnly),
    queryFn: ({ pageParam }) => getNotifications(pageParam, unreadOnly),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.next_cursor ?? undefined : undefined,
    enabled: open,
    refetchInterval: open ? 45_000 : false,
    refetchIntervalInBackground: false,
  });
  useEffect(() => {
    const stream = new EventSource("/api/notifications/stream", { withCredentials: true });
    const refresh = () => {
      void queryClient.invalidateQueries({ queryKey: notificationKeys.all });
    };
    stream.addEventListener("notification", refresh);
    stream.addEventListener("open", refresh);
    return () => {
      stream.removeEventListener("notification", refresh);
      stream.removeEventListener("open", refresh);
      stream.close();
    };
  }, [queryClient]);

  const refreshQueries = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  ]);
  const readMutation = useMutation({ mutationFn: markNotificationRead, onSuccess: refreshQueries });
  const dismissMutation = useMutation({ mutationFn: dismissNotification, onSuccess: refreshQueries });
  const readAllMutation = useMutation({ mutationFn: markAllNotificationsRead, onSuccess: refreshQueries });

  const count = unread.data?.unread_count ?? 0;
  const notifications = page.data?.pages.flatMap((notificationPage) => notificationPage.items) ?? [];
  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger render={<Button variant="ghost" size="icon" aria-label={count ? `${count} unread notifications` : "Notifications"} className="relative"/>}>
      <Bell size={16}/>{count > 0 && <span className="absolute right-1 top-1 grid min-h-3.5 min-w-3.5 place-items-center rounded-full bg-primary px-0.5 text-[8px] font-bold leading-none text-primary-foreground">{count > 99 ? "99+" : count}</span>}
    </PopoverTrigger>
    <PopoverContent align="end" side="bottom" className="w-[min(390px,calc(100vw-1rem))] gap-0 overflow-hidden p-0">
      <PopoverHeader className="flex flex-row items-center justify-between border-b border-border px-4 py-3">
        <div><PopoverTitle>Notifications</PopoverTitle><p className="mt-0.5 text-xs text-muted-foreground">{count} unread</p></div>
      </PopoverHeader>
      <>
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <div className="inline-flex rounded-md bg-muted p-0.5" role="tablist" aria-label="Notification filter">
            <button role="tab" aria-selected={!unreadOnly} className={`rounded px-2.5 py-1 text-xs ${!unreadOnly ? "bg-background font-medium text-foreground shadow-sm" : "text-muted-foreground"}`} onClick={() => setUnreadOnly(false)}>All</button>
            <button role="tab" aria-selected={unreadOnly} className={`rounded px-2.5 py-1 text-xs ${unreadOnly ? "bg-background font-medium text-foreground shadow-sm" : "text-muted-foreground"}`} onClick={() => setUnreadOnly(true)}>Unread</button>
          </div>
          {count > 0 && <Button variant="ghost" size="sm" disabled={readAllMutation.isPending} onClick={() => readAllMutation.mutate()}><CheckCheck size={14}/>Mark all read</Button>}
        </div>
        <div className="max-h-[min(440px,calc(100dvh-10rem))] overflow-y-auto">
          {page.isPending && <p role="status" className="px-4 py-10 text-center text-sm text-muted-foreground">Loading notifications…</p>}
          {page.isError && <div className="px-4 py-8 text-center"><p className="text-sm text-muted-foreground">Notifications could not be loaded.</p><Button variant="outline" size="sm" className="mt-3" onClick={() => void page.refetch()}>Try again</Button></div>}
          {!page.isPending && !page.isError && notifications.length === 0 && <div className="px-4 py-10 text-center"><span className="mx-auto grid size-9 place-items-center rounded-full bg-muted text-muted-foreground"><Inbox size={17}/></span><p className="mt-3 text-sm font-medium">You’re all caught up</p><p className="mt-1 text-xs text-muted-foreground">New assignment and customer updates will appear here.</p></div>}
          {notifications.map((item) => <div key={item.id} className={`group relative border-b border-border/70 px-3 py-3 transition-colors hover:bg-muted/50 ${item.read_at ? "" : "bg-primary/[0.035]"}`}>
            <Link href={internalHref(item)} onClick={() => { if (!item.read_at) readMutation.mutate(item.id); setOpen(false); }} className="flex gap-3 pr-7 outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <span className={`mt-1.5 size-2 shrink-0 rounded-full ${item.read_at ? "bg-transparent" : "bg-primary"}`} aria-hidden="true"/>
              <span className="min-w-0 flex-1"><span className="flex items-start justify-between gap-2"><span className="truncate text-sm font-medium text-foreground">{item.title}</span><time className="shrink-0 text-[11px] text-muted-foreground" dateTime={item.created_at}>{relativeTime(item.created_at)}</time></span><span className="mt-1 block truncate text-xs text-muted-foreground">{item.body}</span></span>
            </Link>
            <div className="absolute right-2 top-2 flex opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
              {!item.read_at && <Button variant="ghost" size="icon-sm" aria-label="Mark as read" onClick={() => readMutation.mutate(item.id)}><Check size={13}/></Button>}
              <Button variant="ghost" size="icon-sm" aria-label="Dismiss notification" onClick={() => dismissMutation.mutate(item.id)}><X size={13}/></Button>
            </div>
          </div>)}
          {page.hasNextPage && <div className="p-2 text-center"><Button variant="ghost" size="sm" loading={page.isFetchingNextPage} onClick={() => void page.fetchNextPage()}>Load more</Button></div>}
        </div>
        <div className="border-t border-border px-3 py-2.5"><Link href="/dashboard/settings#notifications" onClick={() => setOpen(false)} className="text-xs font-medium text-primary hover:underline">Manage notification preferences</Link></div>
      </>
    </PopoverContent>
  </Popover>;
}
