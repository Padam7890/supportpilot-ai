import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { ArrowDown, ArrowUp, ClipboardList, Filter, Move, Plus, Redo2, Trash2, Undo2, Zap } from "lucide-react";
import { defaultCanvasLayout, WORKFLOW_CANVAS } from "../utils/canvas-layout";
import type { CanvasPosition, Condition, DraftStep, WorkflowCanvasLayout, WorkflowDraft } from "../types/workflow-draft";

const CANVAS_WIDTH = WORKFLOW_CANVAS.contentWidth;
const NODE_WIDTH = WORKFLOW_CANVAS.nodeWidth;
const NODE_X_MAX = CANVAS_WIDTH - NODE_WIDTH;
const NODE_Y_MAX = 1800;
const CANVAS_BOTTOM_PADDING = 120;
/** Grid lines for the scroll region (same tint as node cards’ canvas area). */
const CANVAS_GRID_BG =
  "linear-gradient(#e2e8f0 1px, transparent 1px), linear-gradient(90deg, #e2e8f0 1px, transparent 1px)";
const KEYBOARD_MOVE_STEP = 24;
/** Visual height for connectors (reference cards are ~single block; keep stable for straight segments). */
const canvasNodeHeight = 120;
const nodeClass =
  "absolute z-10 box-border min-h-[120px] w-[min(400px,calc(100%-48px))] max-w-[400px] rounded-lg border bg-white p-3.5 text-left text-sm leading-snug text-slate-900 shadow-sm";
const addStepCircleClass =
  "flex size-6 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/15";
const addStepPopoverClass =
  "absolute left-1/2 top-full z-30 mt-1 flex min-w-[9rem] -translate-x-1/2 flex-col rounded-md border border-slate-200 bg-white py-0.5 shadow-md";
const addStepPopoverItemClass =
  "w-full px-2.5 py-1.5 text-left text-[11px] font-medium text-slate-700 hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500/20";

type CanvasNode =
  | { kind: "trigger" }
  | { kind: "condition"; index: number }
  | { kind: "action"; index: number };

type DragState = { node: CanvasNode; clientX: number; clientY: number; initialLayout: WorkflowCanvasLayout };

function connectorNodeKey(node: CanvasNode): string {
  return node.kind === "trigger" ? "trigger" : `${node.kind}-${node.index}`;
}

function isSameConnectorOpen(open: CanvasNode | null, node: CanvasNode): boolean {
  if (!open) return false;
  if (open.kind === "trigger" && node.kind === "trigger") return true;
  if (open.kind === "condition" && node.kind === "condition") return open.index === node.index;
  if (open.kind === "action" && node.kind === "action") return open.index === node.index;
  return false;
}

const fallbackX = Math.round((WORKFLOW_CANVAS.contentWidth - WORKFLOW_CANVAS.nodeWidth) / 2);

function nodePosition(layout: WorkflowCanvasLayout, node: CanvasNode): CanvasPosition {
  const conds = layout.conditions ?? [];
  const acts = layout.actions ?? [];
  if (node.kind === "condition") {
    const fallback = defaultCanvasLayout(node.index + 1, 1).conditions[node.index];
    return conds[node.index] ?? fallback ?? { x: fallbackX, y: 200 };
  }
  if (node.kind === "action") {
    const fallback = defaultCanvasLayout(conds.length, node.index + 1).actions[node.index];
    return acts[node.index] ?? fallback ?? { x: fallbackX, y: 352 };
  }
  return layout.trigger;
}

function withNodePosition(layout: WorkflowCanvasLayout, node: CanvasNode, position: CanvasPosition): WorkflowCanvasLayout {
  if (node.kind === "condition") {
    const conditions = [...(layout.conditions ?? [])];
    conditions[node.index] = position;
    return { ...layout, conditions };
  }
  if (node.kind === "action") {
    const actions = [...(layout.actions ?? [])];
    actions[node.index] = position;
    return { ...layout, actions };
  }
  return { ...layout, trigger: position };
}

function boundedPosition(position: CanvasPosition): CanvasPosition {
  return {
    x: Math.max(0, Math.min(NODE_X_MAX, Math.round(position.x))),
    y: Math.max(0, Math.min(NODE_Y_MAX, Math.round(position.y))),
  };
}

function stepMatches(selected: DraftStep | null, node: CanvasNode): boolean {
  if (!selected) return false;
  if (selected.type === "trigger" && node.kind === "trigger") return true;
  if (selected.type === "condition" && node.kind === "condition" && selected.index === node.index) return true;
  if (selected.type === "action" && node.kind === "action" && selected.index === node.index) return true;
  return false;
}

function issueClass(issues: Set<string>, node: CanvasNode) {
  const key = node.kind === "trigger" ? "trigger" : `${node.kind}-${node.index}`;
  return issues.has(key) ? "border-red-300 ring-1 ring-red-200" : "";
}

function conditionSummary(condition: Condition, index: number): string {
  if (condition.kind === "contains_keyword") {
    const v = condition.value.trim();
    return v.length >= 2 ? `Message contains “${v}”` : `Message keyword ${index + 1} (incomplete)`;
  }
  if (condition.kind === "ticket_priority_is") {
    return `Ticket priority ${condition.operator === "is" ? "is" : "is not"} ${condition.value}`;
  }
  if (condition.kind === "ticket_status_is") {
    return `Ticket status ${condition.operator === "is" ? "is" : "is not"} “${condition.value}”`;
  }
  if (condition.kind === "channel_is") {
    return `Channel ${condition.operator === "is" ? "is" : "is not"} “${condition.value}”`;
  }
  if (condition.kind === "conversation_ai_mode_is") {
    return `AI mode is ${condition.mode}`;
  }
  if (condition.kind === "assignee_present") {
    return condition.value ? "Assignee is set" : "Assignee is not set";
  }
  if (condition.kind === "shopify_store_connected") {
    return "Shopify store connected";
  }
  return `Condition ${index + 1}`;
}

function actionSummary(
  action: WorkflowDraft["actions"][number],
  members: Map<string, string> | undefined,
  aiAgents: Map<string, string> | undefined,
): string {
  if (action.kind === "set_priority") {
    const raise = action.only_raise ? " (only raise)" : "";
    return `Set priority to ${action.value}${raise}`;
  }
  if (action.kind === "assign_to_user") {
    const name = members?.get(action.user_id) ?? "teammate";
    const unassigned = action.only_if_unassigned ? ", only if unassigned" : "";
    return `Assign to ${name}${unassigned}`;
  }
  if (action.kind === "set_ticket_status") {
    return `Set status to “${action.value}”`;
  }
  if (action.kind === "set_conversation_ai_mode") {
    return `Set AI mode to ${action.mode}`;
  }
  if (action.kind === "route_to_ai_bot") {
    return `Route future replies to ${aiAgents?.get(action.ai_agent_id) ?? "selected AI bot"}`;
  }
  if (action.kind === "restore_widget_bot_routing") {
    return "Restore configured widget bot routing";
  }
  if (action.kind === "add_internal_note") {
    return "Add internal note";
  }
  if (action.kind === "require_human_approval") {
    return `Wait for Owner/Admin: ${action.summary}`;
  }
  if (action.kind === "lookup_shopify_order") {
    return "Shopify order lookup";
  }
  if (action.kind === "search_shopify_catalog") {
    return "Shopify catalog search";
  }
  if (action.kind === "request_commerce_approval") {
    return `Commerce approval: ${action.summary}`;
  }
  return "Action";
}

export function AutomationNodeCanvas({
  draft,
  canvasLayout,
  onLayoutChange = () => undefined,
  selectedStep,
  onSelectStep,
  validationIssueKeys,
  memberNamesById,
  aiAgentNamesById,
  canUndo = false,
  canRedo = false,
  onUndo = () => undefined,
  onRedo = () => undefined,
  onAddCondition,
  onAddAction,
  onRemoveCondition,
  onRemoveAction,
  onMoveCondition,
  onMoveAction,
}: {
  draft: WorkflowDraft;
  canvasLayout: WorkflowCanvasLayout;
  onLayoutChange?: (layout: WorkflowCanvasLayout) => void;
  selectedStep: DraftStep | null;
  onSelectStep: (step: DraftStep) => void;
  validationIssueKeys: Set<string>;
  memberNamesById?: Map<string, string>;
  aiAgentNamesById?: Map<string, string>;
  canUndo?: boolean;
  canRedo?: boolean;
  onUndo?: () => void;
  onRedo?: () => void;
  onAddCondition: (atIndex: number) => void;
  onAddAction: (atIndex: number) => void;
  onRemoveCondition: (index: number) => void;
  onRemoveAction: (index: number) => void;
  onMoveCondition: (index: number, delta: -1 | 1) => void;
  onMoveAction: (index: number, delta: -1 | 1) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [openAddStepFor, setOpenAddStepFor] = useState<CanvasNode | null>(null);
  const layoutRef = useRef(canvasLayout);
  const zoomRef = useRef(zoom);
  const dragRef = useRef<DragState | null>(null);
  const addStepPopoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    layoutRef.current = canvasLayout;
    zoomRef.current = zoom;
  }, [canvasLayout, zoom]);

  useEffect(() => {
    if (dragRef.current) return;
    layoutRef.current = canvasLayout;
  }, [canvasLayout]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      const el = addStepPopoverRef.current;
      if (!el || !(event.target instanceof Node)) return;
      if (el.contains(event.target)) return;
      setOpenAddStepFor(null);
    }
    document.addEventListener("pointerdown", handlePointerDown, true);
    return () => document.removeEventListener("pointerdown", handlePointerDown, true);
  }, []);

  function commitLayout(nextLayout: WorkflowCanvasLayout) {
    layoutRef.current = nextLayout;
    onLayoutChange(nextLayout);
  }

  function startMove(node: CanvasNode, event: PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragRef.current = {
      node,
      clientX: event.clientX,
      clientY: event.clientY,
      initialLayout: layoutRef.current,
    };
  }

  function moveByPointer(node: CanvasNode, event: PointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    if (
      !drag
      || drag.node.kind !== node.kind
      || (node.kind === "condition" && drag.node.kind === "condition" && drag.node.index !== node.index)
      || (node.kind === "action" && drag.node.kind === "action" && drag.node.index !== node.index)
    ) {
      return;
    }
    const initial = nodePosition(drag.initialLayout, node);
    const scale = zoomRef.current || 1;
    const nextPosition = boundedPosition({
      x: initial.x + (event.clientX - drag.clientX) / scale,
      y: initial.y + (event.clientY - drag.clientY) / scale,
    });
    const nextLayout = withNodePosition(drag.initialLayout, node, nextPosition);
    layoutRef.current = nextLayout;
    onLayoutChange(nextLayout);
  }

  function finishMove() {
    if (!dragRef.current) return;
    dragRef.current = null;
    onLayoutChange(layoutRef.current);
  }

  function cancelMove() {
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;
    onLayoutChange(drag.initialLayout);
  }

  function moveByKeyboard(node: CanvasNode, event: KeyboardEvent<HTMLButtonElement>) {
    const direction = {
      ArrowLeft: [-KEYBOARD_MOVE_STEP, 0],
      ArrowRight: [KEYBOARD_MOVE_STEP, 0],
      ArrowUp: [0, -KEYBOARD_MOVE_STEP],
      ArrowDown: [0, KEYBOARD_MOVE_STEP],
    }[event.key];
    if (!direction) return;
    event.preventDefault();
    const current = nodePosition(layoutRef.current, node);
    commitLayout(withNodePosition(layoutRef.current, node, boundedPosition({
      x: current.x + direction[0],
      y: current.y + direction[1],
    })));
  }

  function positionStyle(node: CanvasNode) {
    const position = nodePosition(canvasLayout, node);
    return { left: position.x, top: position.y };
  }

  function renderMoveHandle(node: CanvasNode, label: string) {
    return (
      <button
        type="button"
        aria-label={`Move ${label} node. Use arrow keys to reposition.`}
        title="Drag to move, or focus and use arrow keys"
        onPointerDown={(event) => startMove(node, event)}
        onPointerMove={(event) => moveByPointer(node, event)}
        onPointerUp={finishMove}
        onPointerCancel={cancelMove}
        onKeyDown={(event) => moveByKeyboard(node, event)}
        className="touch-none cursor-grab rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 active:cursor-grabbing focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/25"
      >
        <Move size={15} aria-hidden="true" />
      </button>
    );
  }

  function nodeKey(node: CanvasNode) {
    return connectorNodeKey(node);
  }

  function nodeHeight(node: CanvasNode) {
    void node;
    return canvasNodeHeight;
  }

  const orderedNodes: CanvasNode[] = [
    { kind: "trigger" },
    ...draft.conditions.map((_, index): CanvasNode => ({ kind: "condition", index })),
    ...draft.actions.map((_, index): CanvasNode => ({ kind: "action", index })),
  ];

  const lastOrderedNode: CanvasNode | undefined = orderedNodes[orderedNodes.length - 1];

  function isLastOrderedNode(node: CanvasNode): boolean {
    if (!lastOrderedNode) return false;
    if (node.kind === "trigger" && lastOrderedNode.kind === "trigger") return true;
    if (node.kind === "condition" && lastOrderedNode.kind === "condition") return node.index === lastOrderedNode.index;
    if (node.kind === "action" && lastOrderedNode.kind === "action") return node.index === lastOrderedNode.index;
    return false;
  }

  const canvasHeight = Math.max(560, ...orderedNodes.map((node) => nodePosition(canvasLayout, node).y + CANVAS_BOTTOM_PADDING));
  /** Unscaled layout height (`transform: scale` does not affect scroll overflow; outer wrapper uses scaled size). */
  const layoutCanvasHeight = Math.max(520, canvasHeight);
  const scaledCanvasWidth = CANVAS_WIDTH * zoom;
  const scaledCanvasHeight = layoutCanvasHeight * zoom;

  const ch = draft.trigger.channel?.trim();
  const triggerSubtitle = ch ? `${ch} · filtered` : "Any channel · every message";
  const matchLabel = draft.conditionMode === "any" ? "Match any" : "Match all";

  /** Smooth vertical flow between nodes (original canvas style). */
  function connectorPath(from: CanvasNode, to: CanvasNode): string {
    const start = nodePosition(canvasLayout, from);
    const end = nodePosition(canvasLayout, to);
    const startX = start.x + NODE_WIDTH / 2;
    const startY = start.y + nodeHeight(from);
    const endX = end.x + NODE_WIDTH / 2;
    const endY = end.y;
    const gap = endY - startY;
    if (gap >= 16) {
      const bend = gap / 2;
      return `M ${startX} ${startY} C ${startX} ${startY + bend}, ${endX} ${endY - bend}, ${endX} ${endY}`;
    }
    const sweep = Math.max(72, Math.abs(endX - startX) / 2);
    const side = endX >= startX ? sweep : -sweep;
    return `M ${startX} ${startY} C ${startX + side} ${startY + 40}, ${endX + side} ${Math.min(endY, startY) - 28}, ${endX} ${endY}`;
  }

  /** + control pinned to the bottom-center of each card (not gap-centered), including the last step. */
  function renderAddStepOnNode(from: CanvasNode) {
    const open = isSameConnectorOpen(openAddStepFor, from);
    const popoverId = `add-step-menu-${connectorNodeKey(from)}`;

    function conditionInsertIndex(): number {
      if (from.kind === "trigger") return 0;
      if (from.kind === "condition") return from.index + 1;
      return draft.conditions.length;
    }

    function actionInsertIndex(): number {
      if (from.kind === "trigger" || from.kind === "condition") return 0;
      return from.index + 1;
    }

    return (
      <div
        ref={open ? addStepPopoverRef : undefined}
        className="pointer-events-auto absolute bottom-0 left-1/2 z-20 flex -translate-x-1/2 translate-y-1/2 flex-col items-center"
      >
        <button
          type="button"
          className={addStepCircleClass}
          aria-expanded={open}
          aria-haspopup="menu"
          aria-controls={popoverId}
          aria-label="Add step after this step"
          title="Add step"
          onClick={(event) => {
            event.stopPropagation();
            setOpenAddStepFor((current) => (isSameConnectorOpen(current, from) ? null : from));
          }}
        >
          <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
        </button>
        {open && (
          <div id={popoverId} role="menu" className={addStepPopoverClass} aria-label="Add step type">
            <button
              type="button"
              role="menuitem"
              className={addStepPopoverItemClass}
              onClick={() => {
                onAddCondition(conditionInsertIndex());
                setOpenAddStepFor(null);
              }}
            >
              Keyword condition
            </button>
            <button
              type="button"
              role="menuitem"
              className={addStepPopoverItemClass}
              onClick={() => {
                onAddAction(actionInsertIndex());
                setOpenAddStepFor(null);
              }}
            >
              Action
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <section aria-label="Automation rule flow" className="relative flex h-full min-h-0 flex-col bg-white">
      <div className="absolute right-2 top-2 z-20 flex items-center gap-0.5 rounded-md border border-slate-200/80 bg-white/95 px-1 py-0.5 text-slate-600 shadow-sm backdrop-blur-sm">
        <button
          type="button"
          aria-label="Zoom out workflow canvas"
          onClick={() => setZoom((value) => Math.max(0.7, Number((value - 0.1).toFixed(2))))}
          className="rounded px-1.5 py-0.5 text-xs font-medium hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/20"
        >
          −
        </button>
        <span className="min-w-9 text-center text-[10px] font-medium tabular-nums text-slate-600">{Math.round(zoom * 100)}%</span>
        <button
          type="button"
          aria-label="Zoom in workflow canvas"
          onClick={() => setZoom((value) => Math.min(1.4, Number((value + 0.1).toFixed(2))))}
          className="rounded px-1.5 py-0.5 text-xs font-medium hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/20"
        >
          +
        </button>
        <span className="mx-0.5 h-3.5 w-px bg-slate-200" aria-hidden />
        <button
          type="button"
          aria-label="Undo workflow edit"
          title="Undo"
          disabled={!canUndo}
          onClick={onUndo}
          className="rounded p-0.5 text-slate-500 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/20"
        >
          <Undo2 size={14} aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Redo workflow edit"
          title="Redo"
          disabled={!canRedo}
          onClick={onRedo}
          className="rounded p-0.5 text-slate-500 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/20"
        >
          <Redo2 size={14} aria-hidden="true" />
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <div
          className="min-h-0 flex-1 overflow-auto bg-[#f8fafc]"
          style={{
            backgroundImage: CANVAS_GRID_BG,
            backgroundSize: "24px 24px",
          }}
          role="region"
          aria-label="Scrollable workflow canvas"
          tabIndex={0}
        >
          <div
            className="relative mx-auto shrink-0"
            style={{
              width: `max(100%, ${scaledCanvasWidth}px)`,
              minHeight: `max(${scaledCanvasHeight}px, 100%)`,
            }}
          >
            <div
              className="absolute left-0 top-0 box-border flex flex-col items-center px-3 pb-16 pt-6 sm:px-5"
              style={{
                width: CANVAS_WIDTH,
                minHeight: 520,
                height: layoutCanvasHeight,
                transform: `scale(${zoom})`,
                transformOrigin: "0 0",
              }}
              data-workflow-canvas-width={CANVAS_WIDTH}
            >
            <svg aria-hidden="true" className="pointer-events-none absolute inset-0 size-full overflow-visible">
              <defs>
                <marker
                  id="automation-canvas-arrow"
                  markerWidth="12"
                  markerHeight="12"
                  refX="11"
                  refY="6"
                  orient="auto"
                  markerUnits="userSpaceOnUse"
                >
                  <path d="M1 1 L11 6 L1 11 Z" fill="#64748b" />
                </marker>
              </defs>
              {orderedNodes.slice(0, -1).map((from, index) => {
                const to = orderedNodes[index + 1]!;
                return (
                  <g key={`${nodeKey(from)}-${nodeKey(to)}-lines`}>
                    <path
                      d={connectorPath(from, to)}
                      fill="none"
                      stroke="#94a3b8"
                      strokeWidth={1.5}
                      strokeLinecap="round"
                      markerEnd="url(#automation-canvas-arrow)"
                    />
                  </g>
                );
              })}
            </svg>

            <div
              data-automation-step="trigger"
              className={`${nodeClass} ${issueClass(validationIssueKeys, { kind: "trigger" })} border-teal-200 ${stepMatches(selectedStep, { kind: "trigger" }) ? "ring-2 ring-teal-500/30" : ""}`}
              style={positionStyle({ kind: "trigger" })}
            >
              <div className="flex h-full items-start gap-3">
                <button
                  type="button"
                  aria-label="Configure trigger: incoming customer message"
                  className="flex min-w-0 flex-1 items-start gap-3 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
                  onClick={() => onSelectStep({ type: "trigger" })}
                >
                  <span className="grid size-8 shrink-0 place-items-center rounded-md bg-teal-50 text-teal-800" aria-hidden="true">
                    <Zap size={16} strokeWidth={2} />
                  </span>
                  <span className="block min-w-0">
                    <span className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500">Trigger</span>
                    <span className="mt-0.5 block text-[15px] font-semibold text-slate-900">When a customer messages you</span>
                    <span className="mt-1 block text-xs text-slate-500">{triggerSubtitle}</span>
                    {draft.trigger.first_message_only && (
                      <span className="mt-1 block text-xs font-medium text-amber-800">First message in conversation only</span>
                    )}
                  </span>
                </button>
                <div className="absolute right-2 top-2">{renderMoveHandle({ kind: "trigger" }, "trigger")}</div>
              </div>
              {!isLastOrderedNode({ kind: "trigger" }) && renderAddStepOnNode({ kind: "trigger" })}
            </div>

            {draft.conditions.map((condition, index) => {
              const node: CanvasNode = { kind: "condition", index };
              return (
                <div
                  key={`c-${index}`}
                  data-automation-step={`condition-${index}`}
                  className={`${nodeClass} ${issueClass(validationIssueKeys, node)} border-slate-200 ${stepMatches(selectedStep, { kind: "condition", index }) ? "ring-2 ring-indigo-500/25" : ""}`}
                  style={positionStyle(node)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <button
                      type="button"
                      aria-label={`Configure condition ${index + 1}: ${conditionSummary(condition, index)}`}
                      className="flex min-w-0 flex-1 items-start gap-3 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/25"
                      onClick={() => onSelectStep({ type: "condition", index })}
                    >
                      <span className="grid size-8 shrink-0 place-items-center rounded-md bg-indigo-50 text-indigo-800" aria-hidden="true">
                        <Filter size={16} strokeWidth={2} />
                      </span>
                      <span className="block min-w-0">
                        <span className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                          Condition {index + 1}
                        </span>
                        <span className="mt-0.5 block text-sm font-semibold text-slate-900">{conditionSummary(condition, index)}</span>
                        <span className="mt-1 block text-xs text-slate-500">{matchLabel}</span>
                      </span>
                    </button>
                    <div className="flex items-center gap-0.5">
                      {renderMoveHandle(node, `condition ${index + 1}`)}
                      <button
                        type="button"
                        aria-label={`Move condition ${index + 1} up`}
                        disabled={index === 0}
                        onClick={(event) => { event.stopPropagation(); onMoveCondition(index, -1); }}
                        className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/25"
                      >
                        <ArrowUp size={14} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Move condition ${index + 1} down`}
                        disabled={index === draft.conditions.length - 1}
                        onClick={(event) => { event.stopPropagation(); onMoveCondition(index, 1); }}
                        className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/25"
                      >
                        <ArrowDown size={14} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Remove condition ${index + 1}`}
                        onClick={(event) => { event.stopPropagation(); onRemoveCondition(index); }}
                        className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/25"
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                  {!isLastOrderedNode(node) && renderAddStepOnNode(node)}
                </div>
              );
            })}

            {draft.actions.map((action, index) => {
              const node: CanvasNode = { kind: "action", index };
              return (
                <div
                  key={`a-${index}`}
                  data-automation-step={`action-${index}`}
                  className={`${nodeClass} ${issueClass(validationIssueKeys, node)} border-slate-200 ${stepMatches(selectedStep, { kind: "action", index }) ? "ring-2 ring-violet-500/25" : ""}`}
                  style={positionStyle(node)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <button
                      type="button"
                      aria-label={`Configure action ${index + 1}: ${actionSummary(action, memberNamesById, aiAgentNamesById)}`}
                      className="flex min-w-0 flex-1 items-start gap-3 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/25"
                      onClick={() => onSelectStep({ type: "action", index })}
                    >
                      <span className="grid size-8 shrink-0 place-items-center rounded-md bg-violet-50 text-violet-800" aria-hidden="true">
                        <ClipboardList size={16} strokeWidth={2} />
                      </span>
                      <span className="block min-w-0">
                        <span className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500">Action {index + 1}</span>
                        <span className="mt-0.5 block text-sm font-semibold text-slate-900">{actionSummary(action, memberNamesById, aiAgentNamesById)}</span>
                      </span>
                    </button>
                    <div className="flex items-center gap-0.5">
                      {renderMoveHandle(node, `action ${index + 1}`)}
                      <button
                        type="button"
                        aria-label={`Move action ${index + 1} up`}
                        disabled={index === 0}
                        onClick={(event) => { event.stopPropagation(); onMoveAction(index, -1); }}
                        className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/25"
                      >
                        <ArrowUp size={14} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Move action ${index + 1} down`}
                        disabled={index === draft.actions.length - 1}
                        onClick={(event) => { event.stopPropagation(); onMoveAction(index, 1); }}
                        className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/25"
                      >
                        <ArrowDown size={14} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Remove action ${index + 1}`}
                        disabled={draft.actions.length <= 1}
                        onClick={(event) => { event.stopPropagation(); onRemoveAction(index); }}
                        className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/25"
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                  {renderAddStepOnNode(node)}
                </div>
              );
            })}
            </div>

            {draft.conditions.length === 0 && (
              <p
                className="pointer-events-none absolute bottom-2 left-3 right-3 z-30 rounded border border-amber-100/90 bg-amber-50/90 px-2 py-1.5 text-[11px] text-amber-950"
                role="status"
              >
                No conditions — matches all messages for this trigger.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
