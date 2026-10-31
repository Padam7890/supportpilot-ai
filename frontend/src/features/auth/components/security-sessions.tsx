"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, MonitorSmartphone, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { listAuthSessions, revokeAuthSession } from "../api/auth-api";

const SESSION_PAGE_SIZE = 25;

export function SecuritySessions() {
  const client = useQueryClient();
  const [offset, setOffset] = useState(0);
  const sessions = useQuery({
    queryKey: ["auth-sessions", offset],
    queryFn: () => listAuthSessions(offset),
  });
  const revoke = useMutation({
    mutationFn: revokeAuthSession,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["auth-sessions"] });
      if (offset > 0 && sessions.data?.items.length === 1) {
        setOffset(Math.max(0, offset - SESSION_PAGE_SIZE));
      }
    },
  });

  const firstSession = sessions.data && sessions.data.total > 0 ? offset + 1 : 0;
  const lastSession = sessions.data ? Math.min(offset + sessions.data.items.length, sessions.data.total) : 0;

  return <section aria-labelledby="security-sessions-title" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
    <div className="flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><ShieldCheck size={19}/></span><div><h2 id="security-sessions-title" className="font-semibold">Security and sessions</h2><p className="mt-1 text-sm text-slate-500">Review active sign-in sessions for your account and revoke refresh access you no longer use.</p></div></div>
    <p className="mt-4 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">Revoking a session prevents it from renewing access. An access token already issued for it can remain valid until its short expiry.</p>
    {sessions.isPending && <div role="status" className="mt-4 h-20 animate-pulse rounded-xl bg-slate-100"/>}
    {sessions.isError && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">Could not load active sessions.</p>}
    {sessions.data && sessions.data.total > 0 && <p className="mt-4 text-xs text-slate-500">Showing {firstSession}–{lastSession} of {sessions.data.total} active sessions</p>}
    {sessions.data?.items.length === 0 && <p className="mt-4 rounded-xl border border-dashed border-slate-200 p-5 text-center text-sm text-slate-500">No active refresh sessions were found.</p>}
    {sessions.data && sessions.data.items.length > 0 && <ul className="mt-4 divide-y divide-slate-100">{sessions.data.items.map((session) => <li key={session.id} className="flex flex-wrap items-center gap-3 py-4 first:pt-0 last:pb-0"><span className="grid size-9 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600"><MonitorSmartphone size={17}/></span><div className="min-w-40 flex-1"><p className="text-sm font-semibold">Sign-in session</p><p className="mt-1 text-xs text-slate-500">Started {new Date(session.created_at).toLocaleString()} · expires {new Date(session.expires_at).toLocaleDateString()}</p></div><Button size="sm" variant="secondary" disabled={revoke.isPending} onClick={() => revoke.mutate(session.id)}>Revoke</Button></li>)}</ul>}
    {sessions.data && sessions.data.total > SESSION_PAGE_SIZE && <nav aria-label="Session pages" className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4"><Button variant="secondary" size="sm" disabled={offset === 0 || sessions.isFetching} onClick={() => setOffset(Math.max(0, offset - SESSION_PAGE_SIZE))}><ArrowLeft size={14}/>Previous</Button><Button variant="secondary" size="sm" disabled={offset + SESSION_PAGE_SIZE >= sessions.data.total || sessions.isFetching} onClick={() => setOffset(offset + SESSION_PAGE_SIZE)}>Next<ArrowRight size={14}/></Button></nav>}
    {revoke.isError && <p role="alert" className="mt-3 text-sm text-red-700">That session could not be revoked. Refresh the list and try again.</p>}
    {revoke.isSuccess && <p role="status" className="mt-3 text-sm text-emerald-700">Session refresh access revoked.</p>}
  </section>;
}
