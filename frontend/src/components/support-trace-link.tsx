import Link from "next/link";

export function SupportTraceLink({ correlationId }: { correlationId: string }) {
  return (
    <Link
      href={{ pathname: "/dashboard/operations", query: { trace: correlationId } }}
      className="break-all font-medium underline underline-offset-2"
      aria-label={`View request trace for ${correlationId}`}
    >
      <code>{correlationId}</code>
    </Link>
  );
}
