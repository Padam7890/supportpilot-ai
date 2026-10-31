"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut, RefreshCw } from "lucide-react";

import { ApiError } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { formatDateTime } from "@/lib/utils";
import { getPlatformOwner, listTenantReviews, platformLogout, platformOwnerQueryKey, reviewTenant, tenantReviewQueryKey } from "../api/platform-api";
import type { TenantReview } from "../types/platform.types";

export default function TenantApprovalDashboard() {
  const router = useRouter();
  const client = useQueryClient();
  const [status, setStatus] = useState("pending");
  const owner = useQuery({ queryKey: platformOwnerQueryKey, queryFn: getPlatformOwner });
  const tenants = useQuery({ queryKey: tenantReviewQueryKey(status), queryFn: () => listTenantReviews(status), enabled: owner.isSuccess });
  const logout = useMutation({
    mutationFn: platformLogout,
    onSettled: () => {
      client.removeQueries({ queryKey: platformOwnerQueryKey });
      router.replace("/platform/login");
    },
  });
  const action = useMutation({
    mutationFn: ({ id, choice }: { id: string; choice: "approve" | "reject" | "reopen" }) => reviewTenant(id, choice),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["platform-tenants"] });
    },
  });

  useEffect(() => {
    if (owner.isError) router.replace("/platform/login");
  }, [owner.isError, router]);

  if (owner.isPending || !owner.data) {
    return <main className="grid min-h-screen place-items-center bg-slate-50"><div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-100 border-t-blue-700"/></main>;
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-5">
          <div><p className="text-xs font-bold uppercase tracking-[0.15em] text-blue-700">SupportPilot platform</p><h1 className="mt-1 text-2xl font-bold">Tenant approvals</h1><p className="mt-1 text-sm text-slate-500">Signed in as {owner.data.email}</p></div>
          <Button variant="secondary" onClick={() => logout.mutate()} disabled={logout.isPending}><LogOut size={16}/> Sign out</Button>
        </header>
        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div><h2 className="text-lg font-semibold">Workspace registrations</h2><p className="mt-1 text-sm text-slate-500">Approve a tenant to enable its first Owner’s account.</p></div>
            <Select aria-label="Filter tenant registrations" className="w-44" value={status} onChange={(event) => setStatus(event.target.value)}><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option></Select>
          </div>
          {action.isError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{action.error instanceof ApiError ? action.error.message : "Unable to update tenant approval."}</p>}
          {tenants.isError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">Unable to load tenant registrations.</p>}
          {tenants.isPending ? <div className="mt-6 h-40 animate-pulse rounded-xl bg-slate-100"/> : tenants.data?.items.length ? <div className="mt-5 overflow-x-auto"><table className="w-full min-w-[820px] text-left text-sm"><thead><tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400"><th className="px-3 py-3">Workspace</th><th className="px-3 py-3">Slug</th><th className="px-3 py-3">Requested by</th><th className="px-3 py-3">Submitted</th><th className="px-3 py-3">Status</th><th className="px-3 py-3">Action</th></tr></thead><tbody className="divide-y divide-slate-100">{tenants.data.items.map((tenant) => <TenantRow key={tenant.id} tenant={tenant} pending={action.isPending} onAction={(choice) => action.mutate({ id: tenant.id, choice })}/>)}</tbody></table></div> : <div className="mt-8 rounded-xl border border-dashed border-slate-200 p-10 text-center"><p className="font-semibold text-slate-700">No {status} registrations</p><p className="mt-1 text-sm text-slate-500">Tenant requests in this state will appear here.</p></div>}
          <p className="mt-4 text-xs text-slate-400">{tenants.data?.total ?? 0} registrations</p>
        </section>
      </div>
    </main>
  );
}

function TenantRow({ tenant, pending, onAction }: { tenant: TenantReview; pending: boolean; onAction: (choice: "approve" | "reject" | "reopen") => void }) {
  return (
    <tr>
      <td className="px-3 py-4 font-semibold text-slate-900">{tenant.name}</td>
      <td className="px-3 py-4 text-slate-600">{tenant.slug}</td>
      <td className="px-3 py-4"><p className="font-medium text-slate-700">{tenant.requester_name ?? "Unknown"}</p><p className="mt-1 text-xs text-slate-500">{tenant.requester_email ?? "No requester email"}</p></td>
      <td className="px-3 py-4 text-slate-500">{formatDateTime(tenant.created_at)}</td>
      <td className="px-3 py-4"><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold capitalize text-slate-700">{tenant.approval_status}</span></td>
      <td className="px-3 py-4"><div className="flex gap-2">{tenant.approval_status === "pending" ? <><Button size="sm" disabled={pending} onClick={() => onAction("approve")}>Approve</Button><Button size="sm" variant="secondary" disabled={pending} onClick={() => onAction("reject")}>Reject</Button></> : tenant.approval_status === "rejected" ? <Button size="sm" variant="secondary" disabled={pending} onClick={() => onAction("reopen")}><RefreshCw size={14}/> Reopen</Button> : <span className="text-xs text-slate-400">No action</span>}</div></td>
    </tr>
  );
}
