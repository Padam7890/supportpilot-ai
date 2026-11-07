import { InboxWorkspace } from "@/features/inbox/components/inbox-workspace";

export default async function InboxPage({
  searchParams,
}: {
  searchParams: Promise<{ overdue_only?: string | string[] }>;
}) {
  const { overdue_only } = await searchParams;
  const overdueOnly = overdue_only === "true";
  return <InboxWorkspace key={String(overdueOnly)} initialOverdueOnly={overdueOnly} />;
}
