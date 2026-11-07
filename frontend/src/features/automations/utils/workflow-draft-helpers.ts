import type { AutomationWorkflow, WorkflowDefinition } from "../api/automation-api";
import type { Action } from "../types/workflow-draft";
import {
  createEmptyCustomerMessageTrigger,
  defaultAction as defaultActionNode,
  defaultKeywordCondition,
  type WorkflowDraft,
} from "../types/workflow-draft";
import { defaultCanvasLayout, fitCanvasLayout } from "./canvas-layout";

export { defaultActionNode as defaultAction };

export const DEFAULT_WORKFLOW_DESCRIPTION =
  "Route and update tickets when customers message your workspace.";

export const EMPTY_DRAFT: WorkflowDraft = {
  name: "",
  description: DEFAULT_WORKFLOW_DESCRIPTION,
  trigger: createEmptyCustomerMessageTrigger(),
  conditionMode: "all",
  conditions: [],
  actions: [defaultActionNode()],
  elseNote: "",
  canvasLayout: defaultCanvasLayout(0, 1),
};

/** Build API definition from editor draft. */
export function workflowDraftDefinition(draft: WorkflowDraft): WorkflowDefinition {
  const trig = draft.trigger;
  return {
    trigger: {
      kind: "customer_message_received",
      channel: trig.channel,
      first_message_only: trig.first_message_only,
      ai_agent_id:
        trig.ai_agent_id != null && String(trig.ai_agent_id).trim() !== ""
          ? String(trig.ai_agent_id).trim()
          : null,
      integration_connection_id:
        trig.integration_connection_id != null && String(trig.integration_connection_id).trim() !== ""
          ? String(trig.integration_connection_id).trim()
          : null,
    },
    condition_mode: draft.conditionMode,
    conditions: draft.conditions,
    actions: draft.actions,
    else_actions: draft.elseNote?.trim()
      ? [{ kind: "add_internal_note", body: draft.elseNote.trim() }]
      : [],
  };
}

export function workflowDraftPayload(draft: WorkflowDraft) {
  return {
    name: draft.name.trim(),
    description: draft.description,
    definition: workflowDraftDefinition(draft),
    canvas_layout: draft.canvasLayout,
  };
}

function normalizeDefinitionTrigger(raw: WorkflowDefinition["trigger"]): WorkflowDraft["trigger"] {
  if (typeof raw === "object" && raw !== null && "kind" in raw && raw.kind === "customer_message_received") {
    return {
      kind: "customer_message_received",
      channel: raw.channel ?? null,
      first_message_only: raw.first_message_only ?? false,
      ai_agent_id: raw.ai_agent_id ?? null,
      integration_connection_id: raw.integration_connection_id ?? null,
    };
  }
  return createEmptyCustomerMessageTrigger();
}

/** Load editor state from saved workflow (supports legacy string trigger). */
export function workflowDraftFrom(workflow: AutomationWorkflow): WorkflowDraft {
  const def = workflow.definition as WorkflowDefinition & { trigger?: unknown };
  const trigger = normalizeDefinitionTrigger(def.trigger as WorkflowDefinition["trigger"]);
  const conditionMode = def.condition_mode ?? "all";
  const conditions = [...(def.conditions ?? [])];
  const actions = def.actions?.length ? [...def.actions] : [defaultActionNode()];
  const elseNote = def.else_actions?.[0]?.body ?? "";
  const layout = fitCanvasLayout(
    workflow.canvas_layout ?? defaultCanvasLayout(conditions.length, actions.length),
    conditions.length,
    actions.length,
  );

  return {
    name: workflow.name,
    description: workflow.description,
    trigger,
    conditionMode,
    conditions,
    actions,
    elseNote,
    canvasLayout: layout,
  };
}

export function issueKeyForStep(step: { type: string; index?: number }): string {
  if (step.type === "trigger") return "trigger";
  if (step.type === "condition" && typeof step.index === "number") return `condition-${step.index}`;
  if (step.type === "action" && typeof step.index === "number") return `action-${step.index}`;
  return "trigger";
}

export function defaultConditionForKind(
  kind: WorkflowDraft["conditions"][number]["kind"],
): WorkflowDraft["conditions"][number] {
  switch (kind) {
    case "contains_keyword":
      return defaultKeywordCondition();
    case "ticket_priority_is":
      return { kind: "ticket_priority_is", operator: "is", value: "normal" };
    case "ticket_status_is":
      return { kind: "ticket_status_is", operator: "is", value: "open" };
    case "channel_is":
      return { kind: "channel_is", operator: "is", value: "widget" };
    case "conversation_ai_mode_is":
      return { kind: "conversation_ai_mode_is", mode: "ai" };
    case "assignee_present":
      return { kind: "assignee_present", value: true };
    case "shopify_store_connected":
      return { kind: "shopify_store_connected" };
    default:
      return defaultKeywordCondition();
  }
}

export function defaultActionForKind(kind: Action["kind"]): Action {
  switch (kind) {
    case "set_priority":
      return { kind: "set_priority", value: "high", only_raise: false };
    case "assign_to_user":
      return { kind: "assign_to_user", user_id: "", only_if_unassigned: false };
    case "assign_to_team":
      return { kind: "assign_to_team", team_id: "", only_if_unassigned: false };
    case "set_ticket_status":
      return { kind: "set_ticket_status", value: "open" };
    case "set_conversation_ai_mode":
      return { kind: "set_conversation_ai_mode", mode: "human" };
    case "route_to_ai_bot":
      return { kind: "route_to_ai_bot", ai_agent_id: "" };
    case "restore_widget_bot_routing":
      return { kind: "restore_widget_bot_routing" };
    case "add_internal_note":
      return { kind: "add_internal_note", body: "" };
    case "require_human_approval":
      return { kind: "require_human_approval", summary: "Review this workflow step", detail: null };
    case "request_commerce_approval":
      return {
        kind: "request_commerce_approval",
        summary: "Customer requested order cancellation",
        detail: null,
        order_number_regex: "#?[A-Za-z0-9-]{4,}",
      };
    case "lookup_shopify_order":
      return { kind: "lookup_shopify_order", order_number_regex: "#?[A-Za-z0-9-]{4,}" };
    case "search_shopify_catalog":
      return { kind: "search_shopify_catalog", query_regex: null, max_results: 3 };
    default:
      return defaultActionNode();
  }
}
