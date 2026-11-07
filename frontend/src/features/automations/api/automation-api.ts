import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type WorkflowDefinition = components["schemas"]["WorkflowDefinition"];
export type WorkflowCanvasLayout = components["schemas"]["WorkflowCanvasLayout"];
export type AutomationPreviewRequest = components["schemas"]["AutomationPreviewRequest"];
export type AutomationPreview = components["schemas"]["AutomationPreviewOut"];
export type AutomationWorkflow = components["schemas"]["WorkflowOut"];
export type AutomationExecution = components["schemas"]["AutomationExecutionOut"];
export type AutomationMetrics = components["schemas"]["AutomationMetricsOut"];
export type AutomationWorkflowVersion = components["schemas"]["WorkflowVersionHistoryOut"];
export type AutomationWorkflowRestore = components["schemas"]["WorkflowRestoreOut"];
export type AutomationTemplate = components["schemas"]["AutomationTemplateOut"];
export type AutomationApproval = components["schemas"]["AutomationApprovalQueueItem"];

export const automationKey = ["automations"] as const;
export const listAutomations = () => api<AutomationWorkflow[]>("/automations");
export const listAutomationTemplates = (params?: { category?: string }) => {
  const sp = new URLSearchParams();
  if (params?.category) sp.set("category", params.category);
  const qs = sp.toString();
  return api<AutomationTemplate[]>(`/automations/templates${qs ? `?${qs}` : ""}`);
};
export const createAutomationFromTemplate = (values: {
  template_id: string;
  name?: string | null;
  description?: string | null;
}) => api<AutomationWorkflow>("/automations/workflows/from-template", { method: "POST", body: JSON.stringify(values) });
export const previewAutomation = (values: AutomationPreviewRequest) =>
  api<AutomationPreview>("/automations/preview", { method: "POST", body: JSON.stringify(values) });
export const getAutomationMetrics = (days = 30, startDate?: string, endDate?: string) => {
  const params = new URLSearchParams({ days: String(days) });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  return api<AutomationMetrics>(`/automations/metrics?${params.toString()}`);
};
export const createAutomation = (values: {
  name: string;
  description: string | null;
  definition: WorkflowDefinition;
  canvas_layout: WorkflowCanvasLayout;
}) => api<AutomationWorkflow>("/automations", { method: "POST", body: JSON.stringify(values) });
export const updateAutomation = (
  id: string,
  values: {
    name: string;
    description: string | null;
    definition: WorkflowDefinition;
    canvas_layout: WorkflowCanvasLayout;
  },
) => api<AutomationWorkflow>(`/automations/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(values) });
export const publishAutomation = (id: string) =>
  api<{ workflow_id: string; version: number; status: string }>(`/automations/${encodeURIComponent(id)}/publish`, { method: "POST" });
export const pauseAutomation = (id: string) =>
  api<AutomationWorkflow>(`/automations/${encodeURIComponent(id)}/pause`, { method: "POST" });
export const resumeAutomation = (id: string) =>
  api<AutomationWorkflow>(`/automations/${encodeURIComponent(id)}/resume`, { method: "POST" });
export const listAutomationExecutions = (id: string) => api<AutomationExecution[]>(`/automations/${encodeURIComponent(id)}/executions`);
export const retryAutomationExecution = (workflowId: string, executionId: string) =>
  api<AutomationExecution>(
    `/automations/${encodeURIComponent(workflowId)}/executions/${encodeURIComponent(executionId)}/retry`,
    { method: "POST" },
  );
export const listAutomationApprovals = (limit = 50) =>
  api<AutomationApproval[]>(`/automations/approvals?limit=${limit}`);
export const decideAutomationApproval = (
  approval: AutomationApproval,
  decision: "approve" | "reject",
) => api<AutomationExecution>(
  `/automations/${encodeURIComponent(approval.workflow_id)}/executions/${encodeURIComponent(approval.execution_id)}/approvals/${approval.action_index}/${decision}`,
  { method: "POST" },
);
export const listAutomationVersions = (id: string) =>
  api<AutomationWorkflowVersion[]>(`/automations/${encodeURIComponent(id)}/versions`);
export const restoreAutomationVersion = (id: string, version: number) =>
  api<AutomationWorkflowRestore>(`/automations/${encodeURIComponent(id)}/versions/${version}/restore`, { method: "POST" });
