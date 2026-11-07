import { InboxWorkspace } from "@/features/inbox/components/inbox-workspace";

export default async function InboxPage({
  searchParams,
}: {
  searchParams: Promise<{ overdue_only?: string | string[]; channel?: string | string[] }>;
}) {
  const { overdue_only, channel } = await searchParams;
  const overdueOnly = overdue_only === "true";
  const initialChannel = typeof channel === "string" && /^[a-z0-9_]{1,30}$/.test(channel) ? channel : "";
  return <InboxWorkspace key={`${overdueOnly}:${initialChannel}`} initialOverdueOnly={overdueOnly} initialChannel={initialChannel} />;
}
