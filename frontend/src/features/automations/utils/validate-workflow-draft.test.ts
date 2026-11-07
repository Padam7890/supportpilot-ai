import { describe, expect, it } from "vitest";
import { createEmptyCustomerMessageTrigger, defaultAction, type WorkflowDraft } from "../types/workflow-draft";
import { defaultCanvasLayout, fitCanvasLayout } from "./canvas-layout";
import { validateWorkflowDraft } from "./validate-workflow-draft";

const validDraft: WorkflowDraft = {
  name: "Refund triage",
  description: null,
  trigger: createEmptyCustomerMessageTrigger(),
  conditionMode: "all",
  conditions: [{ kind: "contains_keyword" as const, value: "refund" }],
  actions: [defaultAction()],
  canvasLayout: defaultCanvasLayout(1, 1),
};

describe("validateWorkflowDraft", () => {
  it.each([
    { name: "blank name", draft: { ...validDraft, name: "   " }, error: "workflow name" },
    { name: "short keyword", draft: { ...validDraft, conditions: [{ kind: "contains_keyword" as const, value: "x" }] }, error: "needs at least 2" },
    { name: "blank keyword", draft: { ...validDraft, conditions: [{ kind: "contains_keyword" as const, value: "   " }] }, error: "needs at least 2" },
    {
      name: "too many conditions",
      draft: (() => {
        const conditions = Array.from(
          { length: 11 },
          (): WorkflowDraft["conditions"][number] => ({ kind: "contains_keyword", value: "refund" }),
        );
        return {
          ...validDraft,
          conditions,
          canvasLayout: fitCanvasLayout(validDraft.canvasLayout, conditions.length, validDraft.actions.length),
        };
      })(),
      error: "no more than 10 conditions",
    },
    { name: "missing assignee", draft: { ...validDraft, actions: [{ kind: "assign_to_user" as const, user_id: "", only_if_unassigned: false }] }, error: "choose an active teammate" },
    { name: "missing action", draft: { ...validDraft, actions: [] }, error: "Add at least one action" },
  ])("reports an actionable error for $name", ({ draft, error }) => {
    expect(validateWorkflowDraft(draft).errors.join(" ")).toContain(error);
  });

  it("warns when a rule has no message conditions", () => {
    expect(validateWorkflowDraft({ ...validDraft, conditions: [], canvasLayout: defaultCanvasLayout(0, 1) }).warnings).toEqual([
      "No conditions means this rule runs on every matching incoming message and may change tickets broadly.",
    ]);
  });

  it("accepts a valid constrained draft", () => {
    expect(validateWorkflowDraft(validDraft)).toEqual({ errors: [], warnings: [], issues: [] });
  });
});
