import { InboxWorkspace } from "@/features/inbox/components/inbox-workspace";

export default async function InboxPage({
  searchParams,
}: {
  searchParams: Promise<{ overdue_only?: string | string[]; sla_status?: string | string[]; channel?: string | string[] }>;
}) {
  const { overdue_only, sla_status, channel } = await searchParams;
  const overdueOnly = overdue_only === "true";
  const initialSlaStatus = typeof sla_status === "string" ? sla_status : undefined;
  const initialChannel = typeof channel === "string" && /^[a-z0-9_]{1,30}$/.test(channel) ? channel : "";
  return <InboxWorkspace key={`${overdueOnly}:${initialSlaStatus ?? ""}:${initialChannel}`} initialOverdueOnly={overdueOnly} initialSlaStatus={initialSlaStatus} initialChannel={initialChannel} />;
}
