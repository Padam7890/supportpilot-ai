"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { getWorkspaceAudit } from "../api/organization-api";

const PAGE_SIZE = 50;

export function WorkspaceAuditHistory() {
  const [offset, setOffset] = useState(0);
  const audit = useQuery({
    queryKey: ["workspace-audit", offset],
    queryFn: () => getWorkspaceAudit(offset),
  });

  return (
    <section aria-labelledby="workspace-audit-title" className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="workspace-audit-title" className="font-semibold text-slate-900">Workspace activity</h3>
          <p className="mt-1 text-sm text-slate-500">Recent configuration, team, integration, commerce, and ticket events.</p>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">Admin history</span>
      </div>

      {audit.isPending ? (
        <p role="status" className="mt-5 text-sm text-slate-500">Loading workspace activity…</p>
      ) : audit.isError ? (
        <div role="alert" className="mt-5 rounded-xl bg-red-50 p-4 text-sm text-red-700">
          <p>Workspace activity could not be loaded.</p>
          <Button type="button" variant="secondary" size="sm" className="mt-3" onClick={() => audit.refetch()}>Try again</Button>
        </div>
      ) : audit.data.items.length === 0 ? (
        <p className="mt-5 rounded-xl border border-dashed border-slate-300 p-5 text-sm text-slate-500">No workspace activity has been recorded yet.</p>
      ) : (
        <>
          <ol className="mt-5 divide-y divide-slate-100 rounded-xl border border-slate-200">
            {audit.data.items.map((item) => (
              <li key={`${item.category}-${item.id}`} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800">
                    <span className="mr-2 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">{item.category}</span>
                    {formatEvent(item.event_type)}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">{item.actor_name}</p>
                </div>
                <time className="text-xs text-slate-500" dateTime={item.created_at}>{formatTimestamp(item.created_at)}</time>
              </li>
            ))}
          </ol>
          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-xs text-slate-500">Showing {offset + 1}–{offset + audit.data.items.length} of {audit.data.total}</p>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}>Previous</Button>
              <Button type="button" variant="secondary" size="sm" disabled={offset + audit.data.items.length >= audit.data.total} onClick={() => setOffset((current) => current + PAGE_SIZE)}>Next</Button>
            </div>
          </div>
        </>
      )}
      <p className="mt-4 text-xs leading-5 text-slate-500">Audit details, customer messages, provider payloads, and credentials are not included in this summary.</p>
    </section>
  );
}

function formatEvent(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString();
}
