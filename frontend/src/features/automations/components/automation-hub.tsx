"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Activity, Check, GitBranch, Pause, Play, Plus, Workflow, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import {
  automationKey,
  decideAutomationApproval,
  getAutomationMetrics,
  listAutomationApprovals,
  listAutomations,
  pauseAutomation,
  publishAutomation,
  resumeAutomation,
} from "../api/automation-api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AutomationWorkflow } from "../api/automation-api";

export function AutomationHub() {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const canManage = me.data?.role === "owner" || me.data?.role === "admin";
  const workflows = useQuery({ queryKey: automationKey, queryFn: listAutomations });
  const metrics = useQuery({ queryKey: [...automationKey, "metrics"], queryFn: () => getAutomationMetrics() });
  const approvals = useQuery({
    queryKey: [...automationKey, "approvals"],
    queryFn: () => listAutomationApprovals(),
    enabled: canManage,
    refetchInterval: 30_000,
  });

  const changeState = useMutation({
    mutationFn: async ({ workflow, action }: { workflow: AutomationWorkflow; action: "publish" | "pause" | "resume" }) => {
      if (action === "publish") await publishAutomation(workflow.id);
      else if (action === "pause") await pauseAutomation(workflow.id);
      else await resumeAutomation(workflow.id);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: automationKey }),
  });
  const decideApproval = useMutation({
    mutationFn: ({ approvalId, decision }: { approvalId: string; decision: "approve" | "reject" }) => {
      const approval = approvals.data?.find((item) => item.id === approvalId);
      if (!approval) throw new Error("Approval request is no longer available");
      return decideAutomationApproval(approval, decision);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...automationKey, "approvals"] });
      void queryClient.invalidateQueries({ queryKey: automationKey });
    },
  });

  return (
    <div className="h-full overflow-y-auto bg-background text-foreground">
      <header className="border-b border-border bg-background px-4 py-3">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="sidebar-group text-[var(--text-muted)]">Automations</p>
            <h1 className="page-title mt-0.5">Workflows</h1>
            <p className="page-subtitle mt-1.5 max-w-xl">Triggers, conditions, and actions for your inbox. Publish to go live.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/dashboard/automations/templates">
              <Button type="button" variant="secondary" className="border-slate-200">
                Browse templates
              </Button>
            </Link>
            {canManage && (
              <Link href="/dashboard/automations?edit=new">
                <Button type="button" className="bg-teal-700 hover:bg-teal-800 focus-visible:ring-teal-500/30">
                  <Plus size={16} /> New workflow
                </Button>
              </Link>
            )}
          </div>
        </div>
      </header>
      <div className="space-y-5 px-4 py-4">
        <section aria-label="Automation performance, last 30 days" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[
            { label: "Executions", value: metrics.data?.total },
            { label: "Succeeded", value: metrics.data?.succeeded },
            { label: "Failed", value: metrics.data?.failed },
            { label: "Expired approvals", value: metrics.data?.expired },
            { label: "Average duration", value: metrics.data?.average_duration_ms == null ? "—" : `${metrics.data.average_duration_ms} ms` },
          ].map(({ label, value }) => (
            <article key={label} className="rounded-lg border border-slate-200 bg-white p-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
              <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{metrics.isPending ? "…" : metrics.isError ? "—" : value}</p>
            </article>
          ))}
        </section>

        {canManage && (
          <section aria-labelledby="automation-approvals-heading" className="rounded-lg border border-amber-200 bg-amber-50/60 p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 id="automation-approvals-heading" className="text-sm font-semibold text-slate-900">Needs your review</h2>
                <p className="mt-0.5 text-xs text-slate-600">Workflow runs pause at approval steps. Later actions run only after approval.</p>
              </div>
              <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-amber-900">
                {approvals.data?.length ?? (approvals.isPending ? "…" : 0)} pending
              </span>
            </div>
            {approvals.isError ? (
              <p role="alert" className="mt-4 rounded-lg bg-white p-3 text-sm text-red-700">Could not load workflow approvals.</p>
            ) : approvals.isPending ? (
              <p role="status" className="mt-4 rounded-lg bg-white p-3 text-sm text-slate-500">Loading approvals…</p>
            ) : approvals.data.length === 0 ? (
              <p className="mt-4 rounded-lg bg-white p-3 text-sm text-slate-600">No workflow approvals are waiting.</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {approvals.data.map((approval) => (
                  <li key={approval.id} className="flex flex-col justify-between gap-3 rounded-lg border border-amber-200 bg-white p-3 sm:flex-row sm:items-center">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-900">{approval.summary}</p>
                      <p className="mt-0.5 truncate text-xs text-slate-600">{approval.workflow_name} · {approval.ticket_subject}</p>
                      {approval.detail && <p className="mt-1 whitespace-pre-wrap text-xs text-slate-600">{approval.detail}</p>}
                      <p className="mt-1 text-[11px] text-slate-400">Ticket {approval.ticket_id.slice(0, 8)} · requested {new Date(approval.created_at).toLocaleString()} · review by {new Date(approval.expires_at).toLocaleString()}</p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button type="button" size="sm" disabled={decideApproval.isPending} onClick={() => decideApproval.mutate({ approvalId: approval.id, decision: "approve" })}>
                        <Check size={14} /> Approve
                      </Button>
                      <Button type="button" size="sm" variant="secondary" disabled={decideApproval.isPending} onClick={() => decideApproval.mutate({ approvalId: approval.id, decision: "reject" })}>
                        <X size={14} /> Reject
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {decideApproval.isError && <p role="alert" className="mt-3 text-sm text-red-700">Could not save your decision. Refresh the queue and try again.</p>}
          </section>
        )}

        <section aria-labelledby="workflow-list-heading" className="rounded-lg border border-slate-200 bg-white p-4 sm:p-5">
          <h2 id="workflow-list-heading" className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <GitBranch size={16} className="text-slate-500" aria-hidden /> Workflows
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">Drafts do not run until published.</p>

          {workflows.isPending ? (
            <div role="status" className="mt-6 animate-pulse rounded-xl bg-slate-100 p-8 text-center text-sm text-slate-500">Loading workflows…</div>
          ) : workflows.isError ? (
            <div className="mt-6 rounded-xl bg-red-50 p-4 text-sm text-red-700">Could not load workflows.</div>
          ) : workflows.data.length === 0 ? (
            <div className="mt-6 rounded-xl border border-dashed border-slate-300 p-8 text-center">
              <Workflow className="mx-auto text-slate-400" />
              <p className="mt-3 text-sm font-semibold text-slate-800">No workflows yet</p>
              <p className="mt-1 text-sm text-slate-500">{canManage ? "Create a workflow to route and update tickets automatically." : "An admin can create workflows for this workspace."}</p>
            </div>
          ) : (
            <ul className="mt-5 space-y-3">
              {workflows.data.map((workflow) => (
                <li key={workflow.id}>
                  <WorkflowListRow workflow={workflow} canManage={canManage} onState={(action) => changeState.mutate({ workflow, action })} pending={changeState.isPending} />
                </li>
              ))}
            </ul>
          )}
        </section>

        <p className="flex items-center gap-2 text-[11px] text-slate-500">
          <Activity size={14} className="shrink-0 text-slate-400" aria-hidden /> Published workflows run on their configured customer-message events.
        </p>
      </div>
    </div>
  );
}

function summarizeWorkflow(workflow: AutomationWorkflow) {
  const defs = workflow.definition;
  const trig = defs.trigger.kind === "customer_message_received"
    ? "Customer message"
    : defs.trigger.kind === "conversation_started"
      ? "Conversation started"
      : "Inbound ticket created";
  const conds = defs.conditions?.length ?? 0;
  const actLabel = (a: AutomationWorkflow["definition"]["actions"][number]): string => {
    switch (a.kind) {
      case "set_priority":
        return `Priority → ${a.value}`;
      case "assign_to_user":
        return "Assign teammate";
      case "set_ticket_status":
        return `Status → ${a.value}`;
      case "set_conversation_ai_mode":
        return `AI mode → ${a.mode}`;
      case "route_to_ai_bot":
        return "Route to selected AI bot";
      case "restore_widget_bot_routing":
        return "Restore widget bot routing";
      case "add_internal_note":
        return "Internal note";
      case "require_human_approval":
        return `Owner/Admin review: ${a.summary}`;
      case "lookup_shopify_order":
        return "Shopify order lookup";
      case "search_shopify_catalog":
        return "Shopify catalog search";
      case "request_commerce_approval":
        return "Cancellation review";
    }
  };
  const acts = defs.actions.map(actLabel).join("; ");
  return `${trig}${conds ? ` · ${conds} condition${conds === 1 ? "" : "s"}` : " · all messages"} · ${acts}`;
}

function WorkflowListRow({
  workflow,
  canManage,
  onState,
  pending,
}: {
  workflow: AutomationWorkflow;
  canManage: boolean;
  onState: (action: "publish" | "pause" | "resume") => void;
  pending: boolean;
}) {
  const action = workflow.status === "draft" || workflow.has_unpublished_changes ? "publish" : workflow.status === "active" ? "pause" : "resume";
  const actionLabel = action === "publish" ? (workflow.published_version ? "Publish update" : "Publish") : action === "pause" ? "Pause" : "Resume";
  return (
    <article className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-slate-200 bg-white p-3.5 transition-colors hover:border-slate-300">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Link href={`/dashboard/automations/${encodeURIComponent(workflow.id)}`} className="truncate text-sm font-semibold text-slate-900 hover:text-teal-800 hover:underline">
            {workflow.name}
          </Link>
          <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium capitalize ${workflow.status === "active" ? "bg-emerald-50 text-emerald-800" : workflow.status === "paused" ? "bg-amber-50 text-amber-900" : "bg-slate-100 text-slate-600"}`}>{workflow.status}</span>
        </div>
        <p className="mt-1 text-xs text-slate-500">{summarizeWorkflow(workflow)}</p>
        <p className="mt-1 text-[11px] text-slate-400">Published v{workflow.published_version ?? "—"} · Draft v{workflow.draft_version}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link href={`/dashboard/automations?edit=${encodeURIComponent(workflow.id)}`}>
          <Button size="sm" variant="secondary" type="button">Open in builder</Button>
        </Link>
        {canManage && (
          <Button size="sm" variant={action === "pause" ? "secondary" : "primary"} type="button" disabled={pending} onClick={() => onState(action)}>
            {action === "pause" ? <Pause size={14} /> : <Play size={14} />} {actionLabel}
          </Button>
        )}
      </div>
    </article>
  );
}
