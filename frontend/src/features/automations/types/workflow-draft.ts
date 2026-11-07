import type { components } from "@/lib/api/generated";

export type CanvasPosition = components["schemas"]["CanvasPosition"];
type ApiWorkflowCanvasLayout = components["schemas"]["WorkflowCanvasLayout"];
/** Normalized editor layout; API layouts may omit condition/action positions. */
export type WorkflowCanvasLayout = Omit<ApiWorkflowCanvasLayout, "conditions" | "actions"> & {
  conditions: CanvasPosition[];
  actions: CanvasPosition[];
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

/** Editor-only alias; API field is `condition_mode`. */
export type WorkflowDraft = {
  name: string;
  description: string | null;
  trigger: Extract<TriggerConfig, { kind: "customer_message_received" }>;
  conditionMode: "all" | "any";
  conditions: Condition[];
  actions: Action[];
  canvasLayout: WorkflowCanvasLayout;
};

export type DraftStep =
  | { type: "trigger" }
  | { type: "condition"; index: number }
  | { type: "action"; index: number };

export type WorkflowValidationIssue = {
  step: DraftStep;
  message: string;
};

export function createEmptyCustomerMessageTrigger(): WorkflowDraft["trigger"] {
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
