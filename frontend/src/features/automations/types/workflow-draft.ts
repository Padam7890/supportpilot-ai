import type { components } from "@/lib/api/generated";

export type CanvasPosition = components["schemas"]["CanvasPosition"];
type ApiWorkflowCanvasLayout = components["schemas"]["WorkflowCanvasLayout"];
/** Normalized editor layout; API layouts may omit condition/action positions. */
export type WorkflowCanvasLayout = Omit<ApiWorkflowCanvasLayout, "conditions" | "actions"> & {
  conditions: CanvasPosition[];
  actions: CanvasPosition[];
  branch_nodes?: components["schemas"]["WorkflowBranchCanvasPosition"][];
};

export type TriggerConfig = components["schemas"]["WorkflowDefinition"]["trigger"];
export type Condition =
  components["schemas"]["WorkflowDefinition"]["conditions"] extends (infer C)[] | undefined
    ? NonNullable<C>
    : never;
export type Action =
  components["schemas"]["WorkflowDefinition"]["actions"] extends (infer A)[]
    ? A
    : never;
export type WorkflowBranch = components["schemas"]["ConditionalWorkflowBranch"];

/** Editor-only alias; API field is `condition_mode`. */
export type WorkflowDraft = {
  name: string;
  description: string | null;
  trigger: Extract<TriggerConfig, { kind: "customer_message_received" | "conversation_started" | "ticket_created" }>;
  conditionMode: "all" | "any";
  conditions: Condition[];
  actions: Action[];
  branches?: WorkflowBranch[];
  elseNote?: string;
  canvasLayout: WorkflowCanvasLayout;
};

export type DraftStep =
  | { type: "trigger" }
  | { type: "condition"; index: number }
  | { type: "action"; index: number }
  | { type: "branch"; branchId: string };

export type WorkflowValidationIssue = {
  step: DraftStep;
  message: string;
};

export function createEmptyCustomerMessageTrigger(): Extract<WorkflowDraft["trigger"], { kind: "customer_message_received" }> {
  return {
    kind: "customer_message_received",
    channel: null,
    first_message_only: false,
    ai_agent_id: null,
    integration_connection_id: null,
  };
}

export function defaultAction(): Action {
  return { kind: "set_priority", value: "high", only_raise: false };
}

export function defaultKeywordCondition(): Condition {
  return { kind: "contains_keyword", value: "" };
}
