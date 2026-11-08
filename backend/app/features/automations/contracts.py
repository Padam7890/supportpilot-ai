from datetime import date, datetime
import re
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Canvas coordinate bounds align with builder content width (see WORKFLOW_CANVAS.contentWidth).
_CANVAS_X_MAX = 1200
SUPPORTED_TICKET_STATUSES = frozenset({"open", "pending", "resolved", "closed"})


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Triggers (Phase 1: customer_message + stubs for upcoming events) ---

class CustomerMessageTriggerConfig(StrictModel):
    kind: Literal["customer_message_received"] = "customer_message_received"
    channel: str | None = Field(default=None, max_length=40)
    first_message_only: bool = False
    ai_agent_id: UUID | None = None
    integration_connection_id: UUID | None = None


class ConversationStartedTriggerConfig(StrictModel):
    kind: Literal["conversation_started"] = "conversation_started"


class TicketCreatedTriggerConfig(StrictModel):
    kind: Literal["ticket_created"] = "ticket_created"


TriggerConfig = Annotated[
    CustomerMessageTriggerConfig | ConversationStartedTriggerConfig | TicketCreatedTriggerConfig,
    Field(discriminator="kind"),
]


# --- Conditions ---

class ContainsKeywordCondition(StrictModel):
    kind: Literal["contains_keyword"]
    value: str = Field(min_length=2, max_length=80)

    @field_validator("value")
    @classmethod
    def normalize_keyword(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Keyword must contain at least two non-space characters")
        return normalized


class TicketPriorityCondition(StrictModel):
    kind: Literal["ticket_priority_is"]
    operator: Literal["is", "is_not"] = "is"
    value: Literal["low", "normal", "high", "urgent"]


class TicketStatusCondition(StrictModel):
    kind: Literal["ticket_status_is"]
    operator: Literal["is", "is_not"] = "is"
    value: str = Field(min_length=1, max_length=40)


class ChannelCondition(StrictModel):
    kind: Literal["channel_is"]
    operator: Literal["is", "is_not"] = "is"
    value: str = Field(min_length=1, max_length=40)


class ConversationAiModeCondition(StrictModel):
    kind: Literal["conversation_ai_mode_is"]
    mode: Literal["ai", "human"]


class AssigneePresentCondition(StrictModel):
    kind: Literal["assignee_present"]
    value: bool = True


class ShopifyStoreConnectedCondition(StrictModel):
    """True when the workspace has an active Shopify installation (read capability)."""

    kind: Literal["shopify_store_connected"]


Condition = Annotated[
    ContainsKeywordCondition
    | TicketPriorityCondition
    | TicketStatusCondition
    | ChannelCondition
    | ConversationAiModeCondition
    | AssigneePresentCondition
    | ShopifyStoreConnectedCondition,
    Field(discriminator="kind"),
]


# --- Actions ---

class SetPriorityAction(StrictModel):
    kind: Literal["set_priority"]
    value: Literal["low", "normal", "high", "urgent"]
    only_raise: bool = False


class AssignUserAction(StrictModel):
    kind: Literal["assign_to_user"]
    user_id: UUID
    only_if_unassigned: bool = False


class AssignTeamAction(StrictModel):
    kind: Literal["assign_to_team"]
    team_id: UUID
    only_if_unassigned: bool = False


class SetTicketStatusAction(StrictModel):
    kind: Literal["set_ticket_status"]
    value: str = Field(min_length=1, max_length=40)


class SetConversationAiModeAction(StrictModel):
    kind: Literal["set_conversation_ai_mode"]
    mode: Literal["ai", "human"]


class RouteConversationToAgentAction(StrictModel):
    kind: Literal["route_to_ai_bot"]
    ai_agent_id: UUID


class RestoreWidgetBotRoutingAction(StrictModel):
    kind: Literal["restore_widget_bot_routing"]


class AddInternalNoteAction(StrictModel):
    kind: Literal["add_internal_note"]
    body: str = Field(min_length=1, max_length=4000)


class HumanApprovalAction(StrictModel):
    """Pause this execution until a workspace Owner/Admin reviews it."""

    kind: Literal["require_human_approval"]
    summary: str = Field(min_length=2, max_length=200)
    detail: str | None = Field(default=None, max_length=2000)


class RequestCommerceApprovalAction(StrictModel):
    """Request a verified Shopify cancellation for human review (no provider write)."""

    kind: Literal["request_commerce_approval"]
    summary: str = Field(min_length=2, max_length=200)
    detail: str | None = Field(default=None, max_length=2000)
    order_number_regex: str = Field(
        default=r"#?[A-Za-z0-9-]{4,}", min_length=4, max_length=120
    )

    @field_validator("order_number_regex")
    @classmethod
    def validate_order_number_pattern(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError("Order number pattern must be a valid regular expression") from exc
        return value


class LookupShopifyOrderAction(StrictModel):
    """Read-only verified Shopify order lookup; logs an internal note (no outbound customer message)."""

    kind: Literal["lookup_shopify_order"]
    order_number_regex: str = Field(
        default=r"#?[A-Za-z0-9-]{4,}",
        min_length=4,
        max_length=120,
    )


class SearchShopifyCatalogAction(StrictModel):
    """Read-only catalog search against the connected Shopify store; logs titles in an internal note."""

    kind: Literal["search_shopify_catalog"]
    query_regex: str | None = Field(
        default=None,
        max_length=120,
        description="Optional regex with one capture group for the search phrase; defaults to message tail.",
    )
    max_results: int = Field(default=3, ge=1, le=10)


Action = Annotated[
    SetPriorityAction
    | AssignUserAction
    | AssignTeamAction
    | SetTicketStatusAction
    | SetConversationAiModeAction
    | RouteConversationToAgentAction
    | RestoreWidgetBotRoutingAction
    | AddInternalNoteAction
    | HumanApprovalAction
    | RequestCommerceApprovalAction
    | LookupShopifyOrderAction
    | SearchShopifyCatalogAction,
    Field(discriminator="kind"),
]


class ConditionalWorkflowBranch(StrictModel):
    """One ordered rule path, evaluated after the primary condition group."""

    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=80)
    condition_mode: Literal["all", "any"] = "all"
    conditions: list[Condition] = Field(min_length=1, max_length=10)
    actions: list[Action] = Field(min_length=1, max_length=10)

    @field_validator("name")
    @classmethod
    def normalize_branch_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Branch name must contain at least two non-space characters")
        return normalized


class CanvasPosition(StrictModel):
    x: int = Field(ge=0, le=_CANVAS_X_MAX)
    y: int = Field(ge=0, le=1800)


class WorkflowBranchCanvasPosition(StrictModel):
    branch_id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    x: int = Field(ge=0, le=_CANVAS_X_MAX)
    y: int = Field(ge=0, le=1800)


class WorkflowCanvasLayout(StrictModel):
    trigger: CanvasPosition
    conditions: list[CanvasPosition] = Field(default_factory=list, max_length=10)
    actions: list[CanvasPosition] = Field(default_factory=list, max_length=10)
    else_action: CanvasPosition | None = None
    branch_nodes: list[WorkflowBranchCanvasPosition] = Field(default_factory=list, max_length=5)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_single_action_layout(cls, data: Any) -> Any:
        if isinstance(data, dict) and "action" in data and "actions" not in data:
            return {**data, "actions": [data["action"]]}
        return data


def default_canvas_layout(
    condition_count: int,
    action_count: int,
    branch_ids: list[str] | None = None,
) -> WorkflowCanvasLayout:
    trigger_pos = CanvasPosition(x=400, y=48)
    conditions = [CanvasPosition(x=370, y=154 + index * 132) for index in range(condition_count)]
    action_y_base = 180 + condition_count * 132
    actions = [CanvasPosition(x=370, y=action_y_base + index * 132) for index in range(action_count)]
    ids = branch_ids or []
    branch_width = 220
    branch_gap = 12
    start_x = max(16, (1200 - len(ids) * branch_width - max(0, len(ids) - 1) * branch_gap) // 2)
    branch_y = 48 + 148 * (1 + condition_count + action_count) + 180
    branch_nodes = [
        WorkflowBranchCanvasPosition(
            branch_id=branch_id,
            x=start_x + index * (branch_width + branch_gap),
            y=min(1800, branch_y),
        )
        for index, branch_id in enumerate(ids)
    ]
    return WorkflowCanvasLayout(
        trigger=trigger_pos,
        conditions=conditions,
        actions=actions,
        branch_nodes=branch_nodes,
    )


def fit_canvas_layout(
    layout: WorkflowCanvasLayout,
    condition_count: int,
    action_count: int,
    branch_ids: list[str],
) -> WorkflowCanvasLayout:
    defaults = default_canvas_layout(condition_count, action_count, branch_ids)
    current = {node.branch_id: node for node in layout.branch_nodes}
    return WorkflowCanvasLayout(
        trigger=layout.trigger,
        conditions=(layout.conditions + defaults.conditions)[0:condition_count],
        actions=(layout.actions + defaults.actions)[0:action_count],
        else_action=layout.else_action,
        branch_nodes=[current.get(branch_id, default) for branch_id, default in zip(branch_ids, defaults.branch_nodes)],
    )


class WorkflowDefinition(StrictModel):
    trigger: TriggerConfig
    condition_mode: Literal["all", "any"] = "all"
    conditions: list[Condition] = Field(default_factory=list, max_length=10)
    actions: list[Action] = Field(min_length=1, max_length=10)
    branches: list[ConditionalWorkflowBranch] = Field(default_factory=list, max_length=5)
    else_actions: list[AddInternalNoteAction] = Field(default_factory=list, max_length=1)

    @model_validator(mode="after")
    def validate_else_branch(self):
        if self.else_actions and not self.conditions:
            raise ValueError("A no-match branch requires at least one condition")
        if self.branches and not self.conditions:
            raise ValueError("Conditional branches require a primary condition group")
        branch_ids = [branch.id for branch in self.branches]
        if len(branch_ids) != len(set(branch_ids)):
            raise ValueError("Conditional branch IDs must be unique")
        return self

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_definition(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        trig = out.get("trigger")
        if isinstance(trig, str):
            if trig == "customer_message_received":
                out["trigger"] = {"kind": "customer_message_received"}
            else:
                out["trigger"] = {"kind": trig}
        if "condition_mode" not in out:
            out["condition_mode"] = "all"
        return out


class WorkflowCreate(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    definition: WorkflowDefinition
    canvas_layout: WorkflowCanvasLayout | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Workflow name must contain at least two non-space characters")
        return normalized

    @model_validator(mode="after")
    def validate_canvas_layout(self):
        if self.canvas_layout is None:
            return self
        if len(self.canvas_layout.conditions) != len(self.definition.conditions):
            raise ValueError("Canvas layout must include one position for each condition")
        if len(self.canvas_layout.actions) != len(self.definition.actions):
            raise ValueError("Canvas layout must include one position for each action")
        branch_ids = [branch.id for branch in self.definition.branches]
        layout_branch_ids = [node.branch_id for node in self.canvas_layout.branch_nodes]
        if len(layout_branch_ids) != len(set(layout_branch_ids)):
            raise ValueError("Canvas layout branch IDs must be unique")
        if layout_branch_ids and set(layout_branch_ids) != set(branch_ids):
            raise ValueError("Canvas layout must reference the workflow's branch IDs")
        return self


class WorkflowUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    definition: WorkflowDefinition | None = None
    canvas_layout: WorkflowCanvasLayout | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Workflow name must contain at least two non-space characters")
        return normalized


class AutomationPreviewRequest(StrictModel):
    definition: WorkflowDefinition
    sample_message: str = Field(min_length=1, max_length=5000)
    sample_ai_agent_id: UUID | None = None
    sample_integration_connection_id: UUID | None = None
    sample_ticket_priority: Literal["low", "normal", "high", "urgent"] | None = None
    sample_ticket_status: str | None = Field(default=None, max_length=40)
    sample_channel: str | None = Field(default=None, max_length=40)
    sample_is_first_customer_message: bool | None = None
    sample_is_ticket_created: bool | None = None
    sample_assignee_present: bool | None = None
    sample_conversation_ai_mode: Literal["ai", "human"] | None = None
    sample_shopify_connected: bool | None = None

    @field_validator("sample_message")
    @classmethod
    def normalize_sample_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Sample message must not be blank")
        return normalized


class AutomationPreviewConditionOut(StrictModel):
    kind: str
    label: str
    matched: bool


class AutomationPreviewActionOut(StrictModel):
    kind: str
    summary: str
    outcome: Literal["would_run", "skipped"] = "would_run"
    detail: str | None = None


class AutomationPreviewStepOut(StrictModel):
    step: str
    outcome: Literal["matched", "skipped", "would_run", "error"]
    detail: str


class AutomationPreviewOut(StrictModel):
    matches: bool
    condition_mode: Literal["all", "any"]
    conditions: list[AutomationPreviewConditionOut]
    planned_actions: list[AutomationPreviewActionOut]
    steps: list[AutomationPreviewStepOut]
    selected_branch: str | None = None
    assumptions: list[str] = Field(default_factory=list, max_length=12)


class WorkflowOut(StrictModel):
    id: UUID
    name: str
    description: str | None
    status: str
    published_version: int | None
    draft_version: int
    has_unpublished_changes: bool
    definition: WorkflowDefinition
    canvas_layout: WorkflowCanvasLayout


class WorkflowVersionOut(StrictModel):
    workflow_id: UUID
    version: int
    status: str


class WorkflowVersionHistoryOut(StrictModel):
    workflow_id: UUID
    version: int
    created_at: datetime
    is_current: bool


class WorkflowRestoreOut(StrictModel):
    workflow: WorkflowOut
    restored_from_version: int
    message: str


class ExecutionActionOut(StrictModel):
    action_index: int | None = Field(default=None, ge=0)
    action: str
    outcome: Literal["applied", "skipped", "waiting_approval", "approved", "rejected", "expired"]
    detail: str


class AutomationExecutionOut(StrictModel):
    id: UUID
    workflow_id: UUID
    version: int
    conversation_id: UUID
    ticket_id: UUID
    status: str
    attempt_count: int
    retry_available: bool = False
    correlation_id: str | None
    result: list[ExecutionActionOut]
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AutomationApprovalQueueItem(StrictModel):
    id: UUID
    workflow_id: UUID
    workflow_name: str
    execution_id: UUID
    ticket_id: UUID
    ticket_subject: str
    conversation_id: UUID
    action_index: int
    summary: str
    detail: str | None
    created_at: datetime
    expires_at: datetime


class AutomationMetricsDayOut(StrictModel):
    date: date
    total: int
    succeeded: int
    failed: int
    expired: int
    queued: int
    running: int


class AutomationErrorCountOut(StrictModel):
    code: str
    count: int


class AutomationMetricsOut(StrictModel):
    window_start: datetime
    window_end: datetime
    total: int
    queued: int
    running: int
    succeeded: int
    failed: int
    expired: int
    average_duration_ms: int | None
    daily: list[AutomationMetricsDayOut]
    top_errors: list[AutomationErrorCountOut]


class AutomationTemplateOut(StrictModel):
    id: str
    title: str
    description: str
    category: str
    required_capabilities: list[str]
    missing_capabilities: list[str]
    available: bool


class WorkflowTemplateCreate(StrictModel):
    template_id: str = Field(min_length=2, max_length=80)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    canvas_layout: WorkflowCanvasLayout | None = None
