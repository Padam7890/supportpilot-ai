import { describe, expect, it } from "vitest";
import { defaultCanvasLayout, fitCanvasLayout } from "./canvas-layout";

describe("workflow canvas layout", () => {
  it("creates deterministic positions for each condition and action", () => {
    expect(defaultCanvasLayout(2, 1)).toEqual({
      trigger: { x: 400, y: 48 },
      conditions: [{ x: 400, y: 196 }, { x: 400, y: 344 }],
      actions: [{ x: 400, y: 492 }],
    });
  });

  it("preserves dragged positions and safely adds positions for new nodes", () => {
    const initial = defaultCanvasLayout(1, 1);
    initial.conditions[0] = { x: 600, y: 380 };
    initial.actions[0] = { x: 620, y: 500 };
    const fitted = fitCanvasLayout(initial, 2, 2);

    expect(fitted.conditions).toEqual([{ x: 600, y: 380 }, { x: 400, y: 344 }]);
    expect(fitted.actions).toEqual([{ x: 620, y: 500 }, { x: 400, y: 640 }]);
  });

  it("normalizes legacy layouts that omit optional condition and action positions", () => {
    expect(fitCanvasLayout({ trigger: { x: 10, y: 20 } }, 1, 1)).toEqual({
      trigger: { x: 10, y: 20 },
      conditions: [{ x: 400, y: 196 }],
      actions: [{ x: 400, y: 344 }],
    });
  });
});
