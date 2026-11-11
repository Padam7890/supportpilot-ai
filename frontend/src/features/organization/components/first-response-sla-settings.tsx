"use client";

import { Input } from "@/components/ui";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { getFirstResponseSla, updateFirstResponseSla, type FirstResponseSlaPolicy } from "../api/organization-api";

const DEFAULT_POLICY: FirstResponseSlaPolicy = { low: 1440, normal: 480, high: 120, urgent: 30 };
const PRIORITIES: { key: keyof FirstResponseSlaPolicy; label: string }[] = [
  { key: "urgent", label: "Urgent" },
  { key: "high", label: "High" },
  { key: "normal", label: "Normal" },
  { key: "low", label: "Low" },
];

export function FirstResponseSlaSettings() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["organization", "first-response-sla"], queryFn: getFirstResponseSla });
  const [draft, setDraft] = useState<FirstResponseSlaPolicy | null>(null);
  const policy = draft ?? query.data ?? DEFAULT_POLICY;
  const save = useMutation({
    mutationFn: updateFirstResponseSla,
    onSuccess: async (saved) => {
      client.setQueryData(["organization", "first-response-sla"], saved);
      setDraft(null);
      await client.invalidateQueries({ queryKey: ["inbox"] });
    },
  });

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="first-response-sla-title">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700"><Clock3 size={19}/></span>
        <div><h3 id="first-response-sla-title" className="font-semibold text-slate-900">First response targets</h3><p className="mt-1 text-sm text-slate-500">Set elapsed-time targets for the first public team reply after a customer’s first message.</p></div>
      </div>
      {query.isPending ? <p role="status" className="mt-5 text-sm text-slate-500">Loading response targets…</p> : query.isError ? <div role="alert" className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-700"><p>{query.error instanceof ApiError ? query.error.message : "Response targets could not be loaded."}</p><Button variant="unstyled" type="button" className="mt-2 font-semibold underline" onClick={() => query.refetch()}>Try again</Button></div> : (
        <>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {PRIORITIES.map(({ key, label }) => <label key={key} className="block space-y-1.5 text-sm font-medium text-slate-700">{label} priority <span className="font-normal text-slate-400">(minutes)</span><Input type="number" min={5} max={10080} step={5} value={policy[key]} onChange={(event) => setDraft({ ...policy, [key]: Number(event.target.value) })} className="min-h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/20"/></label>)}
          </div>
          <p className="mt-3 text-xs text-slate-500">The clock uses elapsed time, including nights and weekends. Business-hour calendars are not configured.</p>
          <div className="mt-4 flex items-center gap-3"><Button type="button" disabled={save.isPending || query.isPending || PRIORITIES.some(({ key }) => !Number.isInteger(policy[key]) || policy[key] < 5 || policy[key] > 10080)} onClick={() => save.mutate(policy)}>{save.isPending ? "Saving…" : "Save targets"}</Button>{save.isSuccess && <span role="status" className="text-sm text-emerald-700">Targets saved.</span>}</div>
          {save.isError && <p role="alert" className="mt-3 text-sm text-red-700">{save.error instanceof ApiError ? save.error.message : "Response targets could not be saved."}</p>}
        </>
      )}
    </section>
  );
}
