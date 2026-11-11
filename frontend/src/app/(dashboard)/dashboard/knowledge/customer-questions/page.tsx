"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { currentUserQueryKey, getCurrentUser } from "@/features/auth/api/auth-api";
import { KnowledgeGaps } from "@/features/knowledge/components/knowledge-gaps";

export default function CustomerQuestionsPage() {
  const user = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const canReview = user.data?.role === "owner" || user.data?.role === "admin";

  const heading = (
    <div>
      <Link href="/dashboard/knowledge" className="text-sm text-muted-foreground hover:text-foreground">
        Knowledge
      </Link>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">Customer questions</h1>
      <p className="mt-1 text-sm text-muted-foreground">Group similar questions and publish one verified answer for each.</p>
    </div>
  );

  if (canReview) return <KnowledgeGaps heading={heading} />;

  return (
    <div className="space-y-5">
      {heading}
      {user.isPending ? <p role="status" className="text-sm text-muted-foreground">Loading customer questions…</p>
        : user.isError ? <p role="alert" className="text-sm text-destructive">Could not load workspace access.</p>
        : <p className="text-sm text-muted-foreground">Only workspace owners and admins can review customer questions.</p>}
    </div>
  );
}
