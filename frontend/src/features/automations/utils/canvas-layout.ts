import type { WorkflowCanvasLayout as ApiWorkflowCanvasLayout } from "../api/automation-api";
import type { WorkflowCanvasLayout } from "../types/workflow-draft";

/** Builder canvas: modest width, centered nodes (production UI scales in scroll area). */
export const WORKFLOW_CANVAS = {
  contentWidth: 1200,
  nodeWidth: 400,
  verticalStep: 148,
} as const;

const NODE_X = Math.round((WORKFLOW_CANVAS.contentWidth - WORKFLOW_CANVAS.nodeWidth) / 2);

export function defaultCanvasLayout(conditionCount: number, actionCount: number): WorkflowCanvasLayout {
  const triggerY = 48;
  const { verticalStep: step } = WORKFLOW_CANVAS;
  return {
    trigger: { x: NODE_X, y: triggerY },
    conditions: Array.from({ length: conditionCount }, (_, index) => ({
      x: NODE_X,
      y: triggerY + step + index * step,
    })),
    actions: Array.from({ length: actionCount }, (_, index) => ({
      x: NODE_X,
      y: triggerY + step * (1 + conditionCount + index),
    })),
  };
}

export function fitCanvasLayout(
  layout: ApiWorkflowCanvasLayout | null | undefined,
  conditionCount: number,
  actionCount: number,
): WorkflowCanvasLayout {
  const defaults = defaultCanvasLayout(conditionCount, actionCount);
  const existingConds = layout?.conditions ?? [];
  const existingActs = layout?.actions ?? [];
  return {
    trigger: layout?.trigger ?? defaults.trigger,
    conditions: Array.from(
      { length: conditionCount },
      (_, index) => existingConds[index] ?? defaults.conditions[index] ?? {
        x: NODE_X,
        y: 48 + WORKFLOW_CANVAS.verticalStep + index * WORKFLOW_CANVAS.verticalStep,
      },
    ),
    actions: Array.from(
      { length: actionCount },
      (_, index) => existingActs[index] ?? defaults.actions[index] ?? {
        x: NODE_X,
        y: 48 + WORKFLOW_CANVAS.verticalStep * (1 + conditionCount + index),
      },
    ),
  };
}
