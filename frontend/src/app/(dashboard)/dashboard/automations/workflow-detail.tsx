"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ChevronLeft, GitBranch, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import {
  automationKey,
  listAutomationExecutions,
  listAutomationVersions,
  listAutomations,
  pauseAutomation,
  publishAutomation,
  retryAutomationExecution,
  restoreAutomationVersion,
  resumeAutomation,
} from "@/features/automations/api/automation-api";
import type { WorkflowDefinition } from "@/features/automations/api/automation-api";

type WorkflowDetailClientProps = { workflowId: string };

function actionSummary(def: WorkflowDefinition) {
  return def.actions.map((item) => (item.kind === "set_priority" ? "priority" : "assign")).join(", ");
}

export function WorkflowDetailClient({ workflowId }: WorkflowDetailClientProps) {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const canManage = me.data?.role === "owner" || me.data?.role === "admin";

  const workflows = useQuery({ queryKey: automationKey, queryFn: listAutomations });
  const workflow = workflows.data?.find((w) => w.id === workflowId) ?? null;

  const executions = useQuery({
    queryKey: [...automationKey, workflowId, "executions"],
    queryFn: () => listAutomationExecutions(workflowId),
    enabled: Boolean(workflow),
  });
  const versions = useQuery({
    queryKey: [...automationKey, workflowId, "versions"],
    queryFn: () => listAutomationVersions(workflowId),
    enabled: Boolean(workflow),
  });

  const changeState = useMutation({
    mutationFn: async (action: "publish" | "pause" | "resume") => {
      if (!workflow) throw new Error("Missing workflow");
      if (action === "publish") await publishAutomation(workflow.id);
      else if (action === "pause") await pauseAutomation(workflow.id);
      else await resumeAutomation(workflow.id);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: automationKey }),
  });

  const restoreVersion = useMutation({
    mutationFn: (version: number) => restoreAutomationVersion(workflowId, version),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: automationKey });
    },
  });

  const retryExecution = useMutation({
    mutationFn: (executionId: string) => retryAutomationExecution(workflowId, executionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: [...automationKey, workflowId, "executions"] });
      await queryClient.invalidateQueries({ queryKey: [...automationKey, "metrics"] });
    },
  });

  if (workflows.isPending) {
    return (
      <div className="flex h-full items-center justify-center bg-[#f4f7fb] p-8">
        <p className="text-sm text-slate-500">Loading workflow…</p>
      </div>
    );
  }
  if (workflows.isError || !workflow) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-[#f4f7fb] p-8">
        <p className="text-sm text-red-700">Workflow not found.</p>
        <Link href="/dashboard/automations" className="text-sm font-semibold text-teal-700 underline">
          Back to list
        </Link>
      </div>
    );
  }

  const publishAction =
    workflow.status === "draft" || workflow.has_unpublished_changes
      ? "publish"
      : workflow.status === "active"
        ? "pause"
        : "resume";
  const publishLabel =
    publishAction === "publish"
      ? workflow.published_version
        ? "Publish update"
        : "Publish"
      : publishAction === "pause"
        ? "Pause"
        : "Resume";

  return (
    <div className="h-full overflow-y-auto bg-[#f4f7fb]">
      <header className="border-b border-slate-200 bg-white px-4 py-5 sm:px-8">
        <Link
          href="/dashboard/automations"
          className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900"
        >
          <ChevronLeft size={18} aria-hidden /> Automations
        </Link>
        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="grid size-10 place-items-center rounded-xl bg-violet-50 text-violet-700">
                <Workflow size={18} />
              </span>
              <h1 className="text-2xl font-bold tracking-tight text-slate-950">{workflow.name}</h1>
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${
                  workflow.status === "active"
                    ? "bg-emerald-50 text-emerald-700"
                    : workflow.status === "paused"
                      ? "bg-amber-50 text-amber-700"
                      : "bg-slate-100 text-slate-600"
                }`}
              >
                {workflow.status}
              </span>
            </div>
            {workflow.description && <p className="mt-2 max-w-2xl text-sm text-slate-600">{workflow.description}</p>}
            <p className="mt-2 text-xs text-slate-500">
              Live v{workflow.published_version ?? "—"} · Draft v{workflow.draft_version} · {actionSummary(workflow.definition)}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href={`/dashboard/automations?edit=${encodeURIComponent(workflow.id)}`}>
              <Button type="button" variant="secondary" size="sm">
                Edit in builder
              </Button>
            </Link>
            {canManage && (
              <Button
                type="button"
                size="sm"
                variant={publishAction === "pause" ? "secondary" : "primary"}
                disabled={changeState.isPending}
                onClick={() => changeState.mutate(publishAction)}
              >
                {publishLabel}
              </Button>
            )}
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:px-8">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="flex items-center gap-2 font-semibold text-slate-900">
            <GitBranch size={18} className="text-violet-600" /> Run history
          </h2>
          {executions.isPending ? (
            <p className="mt-4 text-sm text-slate-400">Loading…</p>
          ) : executions.isError ? (
            <p className="mt-4 text-sm text-red-600">Could not load executions.</p>
          ) : executions.data.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">No runs yet.</p>
          ) : (
            <ul className="mt-4 space-y-3">
              {executions.data.map((run) => (
                <li key={run.id} className="rounded-xl border border-slate-100 bg-slate-50/80 p-4 text-sm text-slate-700">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <span className="font-medium capitalize">
                      {run.status} · v{run.version} · attempt {run.attempt_count}
                      {run.error_code ? ` · ${run.error_code}` : ""}
                    </span>
                    <div className="flex flex-wrap items-center gap-3">
                      <time dateTime={run.created_at} className="text-xs text-slate-500">
                        {new Date(run.created_at).toLocaleString()}
                      </time>
                      {canManage && run.retry_available && (
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          disabled={retryExecution.isPending}
                          onClick={() => retryExecution.mutate(run.id)}
                        >
                          {retryExecution.isPending ? "Queueing…" : "Retry run"}
                        </Button>
                      )}
                    </div>
                  </div>
                  <details className="mt-2">
                    <summary className="cursor-pointer font-medium text-blue-700">
                      Run details · {run.result.length} steps
                    </summary>
                    <div className="mt-2 border-l-2 border-slate-200 pl-3 text-xs">
                      {run.correlation_id && (
                        <p>
                          Reference: <span className="typo-mono">{run.correlation_id}</span>
                        </p>
                      )}
                      {run.result.length > 0 ? (
                        <ul className="mt-2 space-y-1">
                          {run.result.map((item, index) => (
                            <li key={`${item.action}-${index}`}>
                              <span className="font-medium">{item.action}</span> · {item.outcome} · {item.detail}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-2">No step results recorded.</p>
                      )}
                    </div>
                  </details>
                </li>
              ))}
            </ul>
          )}
          {retryExecution.isError && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">The failed run could not be queued for retry.</p>}
          {retryExecution.isSuccess && <p role="status" className="mt-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">Retry queued with the same published workflow version. Already-applied actions remain protected from duplicate effects.</p>}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="font-semibold text-slate-900">Published versions</h2>
          {versions.isPending ? (
            <p className="mt-4 text-sm text-slate-400">Loading…</p>
          ) : versions.isError ? (
            <p className="mt-4 text-sm text-red-600">Could not load versions.</p>
          ) : versions.data.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">No published versions yet.</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {versions.data.map((v) => (
                <li key={v.version} className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-600">
                  <span>
                    Version {v.version}
                    {v.is_current ? " · active" : ""} · {new Date(v.created_at).toLocaleString()}
                  </span>
                  {canManage && !v.is_current && (
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={restoreVersion.isPending}
                      onClick={() => restoreVersion.mutate(v.version)}
                    >
                      Restore as draft
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {versions.data && versions.data.length > 0 && canManage && (
            <p className="mt-3 text-xs text-slate-500">
              Restoring creates a new draft in the builder; publish to make it live.{" "}
              <Link
                href={`/dashboard/automations?edit=${encodeURIComponent(workflowId)}`}
                className="font-medium text-teal-700 underline"
              >
                Open builder
              </Link>
            </p>
          )}
        </section>

        <p className="flex items-center gap-2 text-xs text-slate-500">
          <ArrowRight size={14} className="shrink-0" />
          Definitions and runs stay on this page; edit triggers and steps in the workflow builder.
        </p>
      </div>
    </div>
  );
}
