import type { WorkflowDraft, WorkflowValidationIssue } from "../types/workflow-draft";

export type WorkflowDraftValidation = {
  errors: string[];
  warnings: string[];
  issues: WorkflowValidationIssue[];
};

const MAX_CONDITIONS = 10;
const MAX_ACTIONS = 10;
const SUPPORTED_TICKET_STATUSES = new Set(["open", "pending", "resolved", "closed"]);

function pushError(
  errors: string[],
  issues: WorkflowValidationIssue[],
  message: string,
  step: WorkflowValidationIssue["step"],
) {
  errors.push(message);
  issues.push({ step, message });
}

function isValidRegex(value: string): boolean {
  try {
    new RegExp(value);
    return true;
  } catch {
    return false;
  }
}

export function validateWorkflowDraft(draft: WorkflowDraft): WorkflowDraftValidation {
  const errors: string[] = [];
  const warnings: string[] = [];
  const issues: WorkflowValidationIssue[] = [];

  if (draft.name.trim().length < 2) {
    errors.push("Add a workflow name with at least 2 characters.");
  } else if (draft.name.trim().length > 120) {
    errors.push("Keep the workflow name to 120 characters or fewer.");
  }

  if (draft.description !== null && draft.description.length > 500) {
    errors.push("Keep the description to 500 characters or fewer.");
  }

  if (draft.trigger.kind === "customer_message_received") {
    if (draft.trigger.channel != null && draft.trigger.channel.trim().length === 0) {
      pushError(errors, issues, "Clear the channel filter or enter a channel name.", { type: "trigger" });
    }
  }

  if (draft.conditions.length > MAX_CONDITIONS) {
    pushError(errors, issues, `Use no more than ${MAX_CONDITIONS} conditions.`, { type: "condition", index: 0 });
  }
  const elseNote = draft.elseNote ?? "";
  if (elseNote.trim() && draft.conditions.length === 0) {
    pushError(errors, issues, "A no-match note requires at least one condition.", { type: "trigger" });
  }
  if (elseNote.length > 4000) {
    pushError(errors, issues, "Keep the no-match internal note to 4,000 characters or fewer.", { type: "trigger" });
  }
  const branches = draft.branches ?? [];
  if (branches.length > 5) {
    pushError(errors, issues, "Use no more than 5 additional condition branches.", { type: "trigger" });
  }
  if (branches.length > 0 && draft.conditions.length === 0) {
    pushError(errors, issues, "Additional condition branches require a primary condition group.", { type: "trigger" });
  }
  const branchIds = new Set<string>();
  const branchRuleKeys = new Set<string>();
  branches.forEach((branch, index) => {
    const branchStep: WorkflowValidationIssue["step"] = { type: "branch", branchId: branch.id };
    if (branchIds.has(branch.id)) {
      pushError(errors, issues, `Branch ${index + 1} has a duplicate identifier. Remove and recreate this path.`, branchStep);
    }
    branchIds.add(branch.id);
    if (branch.name.trim().length < 2) {
      pushError(errors, issues, `Branch ${index + 1} needs a name with at least 2 characters.`, branchStep);
    }
    if (branch.conditions.length === 0) {
      pushError(errors, issues, `Branch ${index + 1} needs at least one condition.`, branchStep);
    }
    const ruleKey = JSON.stringify({
      mode: branch.condition_mode,
      conditions: branch.conditions.map((condition) => JSON.stringify(condition)).sort(),
    });
    if (branchRuleKeys.has(ruleKey)) {
      warnings.push(`Branch “${branch.name}” duplicates an earlier rule and will not be reached when that rule matches first.`);
    }
    branchRuleKeys.add(ruleKey);

    // Reuse the same field-level rules as the primary path, then scope issues to this branch.
    const branchValidation = validateWorkflowDraft({
      ...draft,
      conditions: branch.conditions,
      actions: branch.actions,
      branches: [],
      elseNote: "",
      canvasLayout: {
        ...draft.canvasLayout,
        conditions: branch.conditions.map(() => ({ x: 0, y: 0 })),
        actions: branch.actions.map(() => ({ x: 0, y: 0 })),
        branch_nodes: [],
      },
    });
    for (const issue of branchValidation.issues) {
      if (issue.step.type !== "condition" && issue.step.type !== "action") continue;
      pushError(errors, issues, `Branch ${index + 1}: ${issue.message}`, branchStep);
    }
  });

  const layoutBranchIds = (draft.canvasLayout.branch_nodes ?? []).map((node) => node.branch_id);
  if (layoutBranchIds.length !== branches.length || new Set(layoutBranchIds).size !== layoutBranchIds.length ||
    branches.some((branch) => !layoutBranchIds.includes(branch.id))) {
    const issueStep: WorkflowValidationIssue["step"] = branches[0]
      ? { type: "branch", branchId: branches[0].id }
      : { type: "trigger" };
    pushError(errors, issues, "Canvas layout is out of sync with conditional branches. Use Arrange to repair node positions.", issueStep);
  }

  draft.conditions.forEach((condition, index) => {
    const step: WorkflowValidationIssue["step"] = { type: "condition", index };
    if (condition.kind === "contains_keyword") {
      const normalized = condition.value.trim();
      if (normalized.length < 2) {
        pushError(
          errors,
          issues,
          `Message keyword ${index + 1} needs at least 2 non-space characters.`,
          step,
        );
      } else if (normalized.length > 80) {
        pushError(errors, issues, `Message keyword ${index + 1} must be 80 characters or fewer.`, step);
      }
    } else if (condition.kind === "ticket_priority_is") {
      /* values are enum-bound */
    } else if (condition.kind === "ticket_status_is") {
      if (!SUPPORTED_TICKET_STATUSES.has(condition.value.trim().toLowerCase())) {
        pushError(
          errors,
          issues,
          `Ticket status ${index + 1} must be open, pending, resolved, or closed.`,
          step,
        );
      }
    } else if (condition.kind === "channel_is") {
      if (condition.value.trim().length < 1) {
        pushError(errors, issues, `Channel rule ${index + 1} needs a value.`, step);
      }
    } else if (condition.kind === "conversation_ai_mode_is") {
      /* enum */
    } else if (condition.kind === "assignee_present") {
      /* boolean */
    } else if (condition.kind === "shopify_store_connected") {
      /* flag */
    }
  });

  if (draft.actions.length === 0) {
    pushError(errors, issues, "Add at least one action.", { type: "action", index: 0 });
  }
  if (draft.actions.length > MAX_ACTIONS) {
    pushError(errors, issues, `Use no more than ${MAX_ACTIONS} actions.`, { type: "action", index: 0 });
  }

  draft.actions.forEach((action, index) => {
    const step: WorkflowValidationIssue["step"] = { type: "action", index };
    if (action.kind === "assign_to_user" && !action.user_id) {
      pushError(errors, issues, `Action ${index + 1}: choose an active teammate for assignment.`, step);
    }
    if (action.kind === "assign_to_team" && !action.team_id) {
      pushError(errors, issues, `Action ${index + 1}: choose an active support team.`, step);
    }
    if (action.kind === "route_to_ai_bot" && !action.ai_agent_id) {
      pushError(errors, issues, `Action ${index + 1}: choose an active AI bot for future widget replies.`, step);
    }
    if (action.kind === "set_ticket_status" && !SUPPORTED_TICKET_STATUSES.has(action.value.trim().toLowerCase())) {
      pushError(
        errors,
        issues,
        `Action ${index + 1}: choose open, pending, resolved, or closed as the ticket status.`,
        step,
      );
    }
    if (action.kind === "add_internal_note" && action.body.trim().length < 1) {
      pushError(errors, issues, `Action ${index + 1}: internal note body cannot be blank.`, step);
    }
    if (action.kind === "require_human_approval" && action.summary.trim().length < 2) {
      pushError(errors, issues, `Action ${index + 1}: add a short approval summary.`, step);
    }
    if (action.kind === "request_commerce_approval" && action.summary.trim().length < 2) {
      pushError(errors, issues, `Action ${index + 1}: add a short cancellation review summary.`, step);
    }
    if (
      (action.kind === "lookup_shopify_order" || action.kind === "request_commerce_approval") &&
      (action.order_number_regex.trim().length < 4 || !isValidRegex(action.order_number_regex))
    ) {
      pushError(errors, issues, `Action ${index + 1}: enter a valid order-number pattern with at least 4 characters.`, step);
    }
    if (action.kind === "search_shopify_catalog") {
      if (action.max_results < 1 || action.max_results > 10) {
        pushError(errors, issues, `Action ${index + 1}: catalog search must return 1–10 products.`, step);
      }
    }
  });

  const layoutConds = draft.canvasLayout.conditions ?? [];
  const layoutActs = draft.canvasLayout.actions ?? [];
  if (layoutConds.length !== draft.conditions.length) {
    pushError(errors, issues, "Canvas layout is out of sync with conditions.", { type: "condition", index: 0 });
  }
  if (layoutActs.length !== draft.actions.length) {
    pushError(errors, issues, "Canvas layout is out of sync with actions.", { type: "action", index: 0 });
  }

  if (draft.conditions.length === 0) {
    warnings.push("No conditions means this rule runs on every matching incoming message and may change tickets broadly.");
  }

  return { errors, warnings, issues };
}
