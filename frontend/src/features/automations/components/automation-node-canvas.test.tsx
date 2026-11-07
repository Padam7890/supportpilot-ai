import type { ComponentProps } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AutomationNodeCanvas } from "./automation-node-canvas";
import { EMPTY_DRAFT } from "../utils/workflow-draft-helpers";
import { defaultCanvasLayout } from "../utils/canvas-layout";

afterEach(() => cleanup());

const baseDraft = {
  ...EMPTY_DRAFT,
  conditions: [{ kind: "contains_keyword" as const, value: "refund" }],
  actions: [{ kind: "set_priority" as const, value: "high" as const, only_raise: false }],
};

function renderCanvas(overrides?: Partial<ComponentProps<typeof AutomationNodeCanvas>>) {
  const layout = defaultCanvasLayout(baseDraft.conditions.length, baseDraft.actions.length);
  return render(
    <AutomationNodeCanvas
      draft={{ ...baseDraft, canvasLayout: layout }}
      canvasLayout={layout}
      selectedStep={{ type: "trigger" }}
      onSelectStep={vi.fn()}
      validationIssueKeys={new Set()}
      onLayoutChange={vi.fn()}
      onAddCondition={vi.fn()}
      onAddAction={vi.fn()}
      onRemoveCondition={vi.fn()}
      onRemoveAction={vi.fn()}
      onMoveCondition={vi.fn()}
      onMoveAction={vi.fn()}
      {...overrides}
    />,
  );
}

describe("AutomationNodeCanvas", () => {
  it("provides accessible undo and redo controls for draft history", () => {
    const onUndo = vi.fn();
    const onRedo = vi.fn();
    renderCanvas({ canUndo: true, canRedo: true, onUndo, onRedo });

    fireEvent.click(screen.getByRole("button", { name: "Undo workflow edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Redo workflow edit" }));
    expect(onUndo).toHaveBeenCalledOnce();
    expect(onRedo).toHaveBeenCalledOnce();
  });

  it("shows trigger and condition summaries", () => {
    renderCanvas();
    expect(screen.getByText("When a customer messages you")).toBeInTheDocument();
    expect(screen.getByText(/Message contains/)).toBeInTheDocument();
  });

  it("repositions the trigger node with arrow keys", () => {
    const onLayoutChange = vi.fn();
    renderCanvas({ onLayoutChange });

    fireEvent.keyDown(screen.getByRole("button", { name: /Move trigger node/ }), { key: "ArrowRight" });

    expect(onLayoutChange).toHaveBeenCalledWith(
      expect.objectContaining({
        trigger: { x: 424, y: 48 },
        conditions: expect.any(Array),
        actions: expect.any(Array),
      }),
    );
  });
});
