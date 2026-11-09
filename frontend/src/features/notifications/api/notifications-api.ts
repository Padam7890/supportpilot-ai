import { api, jsonBody } from "@/lib/api/client";

export type NotificationEventType = "ticket.assigned" | "conversation.customer_replied" | "ai.escalation_required";
export type NotificationCategory = "inbox" | "ai" | "automation" | "integration" | "knowledge" | "team" | "system";

export type NotificationItem = {
  id: string;
  event_type: NotificationEventType;
  category: NotificationCategory;
  priority: "low" | "normal" | "high" | "critical";
  title: string;
  body: string | null;
  resource_type: string | null;
  resource_id: string | null;
  action_url: string | null;
  created_at: string;
  read_at: string | null;
};

export type NotificationPage = { items: NotificationItem[]; next_cursor: string | null; has_more: boolean };
export type NotificationPreference = { event_type: NotificationEventType; in_app_enabled: boolean; email_enabled: boolean };
export type NotificationPreferencesUpdate = Partial<Pick<NotificationPreference, "in_app_enabled" | "email_enabled">>;

export const notificationKeys = {
  all: ["notifications"] as const,
  list: (unread = false) => ["notifications", "list", unread] as const,
  unread: () => ["notifications", "unread-count"] as const,
  preferences: () => ["notifications", "preferences"] as const,
};

export const getNotifications = (cursor?: string, unreadOnly = false) => {
  const params = new URLSearchParams({ limit: "30", unread_only: String(unreadOnly) });
  if (cursor) params.set("cursor", cursor);
  return api<NotificationPage>(`/notifications?${params}`);
};

export const getUnreadNotificationCount = () => api<{ unread_count: number }>("/notifications/unread-count");
export const getNotificationPreferences = () => api<NotificationPreference[]>("/notifications/preferences");
export const markNotificationRead = (id: string) => api<void>(`/notifications/${id}/read`, { method: "PATCH" });
export const dismissNotification = (id: string) => api<void>(`/notifications/${id}/dismiss`, { method: "PATCH" });
export const markAllNotificationsRead = () => api<{ affected_count: number }>("/notifications/read-all", { method: "POST" });
export const updateNotificationPreference = (eventType: NotificationEventType, values: NotificationPreferencesUpdate) =>
  api<NotificationPreference>(`/notifications/preferences/${eventType}`, { method: "PATCH", body: jsonBody(values) });
