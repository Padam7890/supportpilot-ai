import type { WorkflowCanvasLayout as ApiWorkflowCanvasLayout } from "../api/automation-api";
import type { WorkflowCanvasLayout } from "../types/workflow-draft";

/** Builder canvas: modest width, centered nodes (production UI scales in scroll area). */
export const WORKFLOW_CANVAS = {
  contentWidth: 1200,
  nodeWidth: 400,
  verticalStep: 148,
} as const;

const NODE_X = Math.round((WORKFLOW_CANVAS.contentWidth - WORKFLOW_CANVAS.nodeWidth) / 2);

export function defaultCanvasLayout(conditionCount: number, actionCount: number, branchIds: string[] = []): WorkflowCanvasLayout {
  const triggerY = 48;
  const { verticalStep: step } = WORKFLOW_CANVAS;
  const branchWidth = 220;
  const branchGap = 12;
  const totalBranchWidth = branchIds.length * branchWidth + Math.max(0, branchIds.length - 1) * branchGap;
  const branchStartX = Math.max(16, (WORKFLOW_CANVAS.contentWidth - totalBranchWidth) / 2);
  const branchY = Math.min(1800, triggerY + step * (1 + conditionCount + actionCount) + 180);
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
    ...(branchIds.length > 0 ? {
      branch_nodes: branchIds.map((branch_id, index) => ({
        branch_id,
        x: branchStartX + index * (branchWidth + branchGap),
        y: branchY,
      })),
    } : {}),
  };
}

export function fitCanvasLayout(
  layout: ApiWorkflowCanvasLayout | null | undefined,
  conditionCount: number,
  actionCount: number,
  branchIds: string[] = [],
): WorkflowCanvasLayout {
  const defaults = defaultCanvasLayout(conditionCount, actionCount, branchIds);
  const existingConds = layout?.conditions ?? [];
  const existingActs = layout?.actions ?? [];
  const existingBranches = new Map((layout?.branch_nodes ?? []).map((node) => [node.branch_id, node]));
  return {
    trigger: layout?.trigger ?? defaults.trigger,
    else_action: layout?.else_action,
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
    ...(branchIds.length > 0 ? {
      branch_nodes: (defaults.branch_nodes ?? []).map((node) => existingBranches.get(node.branch_id) ?? node),
    } : {}),
  };
}
