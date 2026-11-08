"""Curated automation marketplace templates."""

from __future__ import annotations

from typing import Any

from app.features.automations.capabilities import missing_capabilities
from app.features.automations.contracts import WorkflowDefinition, default_canvas_layout

# Template registry: id -> factory(definition overrides from request)
_TEMPLATE_REGISTRY: dict[str, dict[str, Any]] = {}


def _register(meta: dict[str, Any]) -> None:
    _TEMPLATE_REGISTRY[meta["id"]] = meta


def _base_widget_first_message() -> tuple[WorkflowDefinition, dict[str, Any]]:
    definition = WorkflowDefinition.model_validate({
        "trigger": {
            "kind": "customer_message_received",
            "channel": "web",
            "first_message_only": True,
        },
        "condition_mode": "all",
        "conditions": [],
        "actions": [
            {"kind": "set_priority", "value": "normal", "only_raise": False},
            {"kind": "set_ticket_status", "value": "open"},
        ],
    })
    layout = default_canvas_layout(0, len(definition.actions))
    return definition, layout.model_dump(mode="json")


def _template_01() -> tuple[WorkflowDefinition, dict[str, Any]]:
    return _base_widget_first_message()


def _template_route_inbox() -> tuple[WorkflowDefinition, dict[str, Any]]:
    definition = WorkflowDefinition.model_validate({
        "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
        "condition_mode": "any",
        "conditions": [
            {"kind": "contains_keyword", "value": "refund"},
            {"kind": "contains_keyword", "value": "order"},
        ],
        "actions": [
            {"kind": "set_priority", "value": "high", "only_raise": True},
        ],
    })
    return definition, default_canvas_layout(len(definition.conditions), len(definition.actions)).model_dump(
        mode="json"
    )


def _template_faq_knowledge() -> tuple[WorkflowDefinition, dict[str, Any]]:
    definition = WorkflowDefinition.model_validate({
        "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
        "condition_mode": "all",
        "conditions": [
            {"kind": "conversation_ai_mode_is", "mode": "ai"},
        ],
        "actions": [
            {
                "kind": "add_internal_note",
                "body": "[Automation] FAQ branch matched; configure AI send in a follow-up workflow.",
            },
        ],
    })
    return definition, default_canvas_layout(len(definition.conditions), len(definition.actions)).model_dump(
        mode="json"
    )


def _template_shopify_tracking() -> tuple[WorkflowDefinition, dict[str, Any]]:
    definition = WorkflowDefinition.model_validate({
        "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
        "condition_mode": "all",
        "conditions": [
            {"kind": "shopify_store_connected"},
            {"kind": "contains_keyword", "value": "track"},
        ],
        "actions": [
            {"kind": "lookup_shopify_order", "order_number_regex": r"(#?[A-Za-z0-9-]{4,})"},
            {"kind": "set_priority", "value": "normal", "only_raise": True},
        ],
    })
    return definition, default_canvas_layout(len(definition.conditions), len(definition.actions)).model_dump(
        mode="json"
    )


def _template_recommend_npr() -> tuple[WorkflowDefinition, dict[str, Any]]:
    definition = WorkflowDefinition.model_validate({
        "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
        "condition_mode": "all",
        "conditions": [
            {"kind": "shopify_store_connected"},
            {"kind": "contains_keyword", "value": "recommend"},
        ],
        "actions": [
            {"kind": "search_shopify_catalog", "query_regex": None, "max_results": 3},
        ],
    })
    return definition, default_canvas_layout(len(definition.conditions), len(definition.actions)).model_dump(
        mode="json"
    )


def _template_return_review() -> tuple[WorkflowDefinition, dict[str, Any]]:
    definition = WorkflowDefinition.model_validate({
        "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
        "condition_mode": "any",
        "conditions": [
            {"kind": "contains_keyword", "value": "return"},
            {"kind": "contains_keyword", "value": "refund"},
        ],
        "actions": [
            {
                "kind": "add_internal_note",
                "body": "[Automation] Return/refund request — review with Orders policy before any write.",
            },
            {"kind": "set_priority", "value": "high", "only_raise": True},
        ],
    })
    return definition, default_canvas_layout(len(definition.conditions), len(definition.actions)).model_dump(
        mode="json"
    )


def _template_human_handoff() -> tuple[WorkflowDefinition, dict[str, Any]]:
    definition = WorkflowDefinition.model_validate({
        "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
        "condition_mode": "any",
        "conditions": [
            {"kind": "contains_keyword", "value": "human"},
            {"kind": "contains_keyword", "value": "agent"},
        ],
        "actions": [
            {
                "kind": "set_conversation_ai_mode",
                "mode": "human",
            },
            {
                "kind": "add_internal_note",
                "body": "[Automation] Customer asked for a human — AI paused for this conversation.",
            },
        ],
    })
    return definition, default_canvas_layout(len(definition.conditions), len(definition.actions)).model_dump(
        mode="json"
    )


def _register_all() -> None:
    d, layout = _template_01()
    _register({
        "id": "playbook-01-widget-first-ticket",
        "title": "First widget message — open ticket",
        "description": "On the first customer message on the web widget, ensure the ticket stays open at normal priority.",
        "category": "widget",
        "required_capabilities": [],
        "definition": d,
        "canvas_layout": layout,
    })
    d, layout = _template_route_inbox()
    _register({
        "id": "playbook-02-route-keywords",
        "title": "Route by keywords (refund / order)",
        "description": "Raise priority when the customer mentions refund or order.",
        "category": "inbox",
        "required_capabilities": [],
        "definition": d,
        "canvas_layout": layout,
    })
    d, layout = _template_faq_knowledge()
    _register({
        "id": "playbook-03-faq-ai-branch",
        "title": "FAQ path — AI-owned conversation",
        "description": "When AI mode is active, log an internal note for grounded FAQ follow-up.",
        "category": "ai",
        "required_capabilities": [],
        "definition": d,
        "canvas_layout": layout,
    })
    d, layout = _template_shopify_tracking()
    _register({
        "id": "playbook-04-shopify-tracking",
        "title": "Order tracking intent (Shopify)",
        "description": "Requires a connected Shopify store; flags tracking-related messages for verified lookup.",
        "category": "commerce",
        "required_capabilities": ["shopify.orders.verified_read"],
        "definition": d,
        "canvas_layout": layout,
    })
    d, layout = _template_recommend_npr()
    _register({
        "id": "playbook-05-recommend-catalog",
        "title": "Product recommendation hook (Shopify)",
        "description": "Requires Shopify; use as a starting point for catalog-grounded recommendations.",
        "category": "commerce",
        "required_capabilities": ["shopify.catalog.read"],
        "definition": d,
        "canvas_layout": layout,
    })
    d, layout = _template_return_review()
    _register({
        "id": "playbook-06-return-review",
        "title": "Return / refund — review first",
        "description": "Captures return/refund language and raises priority; no provider writes.",
        "category": "commerce",
        "required_capabilities": [],
        "definition": d,
        "canvas_layout": layout,
    })
    d, layout = _template_human_handoff()
    _register({
        "id": "playbook-07-human-handoff",
        "title": "Human handoff — pause AI",
        "description": "When the customer asks for a human, switch conversation to human mode and add a note.",
        "category": "inbox",
        "required_capabilities": [],
        "definition": d,
        "canvas_layout": layout,
    })
    _register({
        "id": "playbook-08-sla-reminder",
        "title": "Urgent ticket — SLA follow-up note",
        "description": "When priority is urgent, add an internal note so the team tracks first-response follow-up.",
        "category": "operations",
        "required_capabilities": [],
        "definition": WorkflowDefinition.model_validate({
            "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
            "condition_mode": "all",
            "conditions": [{"kind": "ticket_priority_is", "operator": "is", "value": "urgent"}],
            "actions": [{"kind": "add_internal_note", "body": "[Automation] Urgent priority — confirm first-response SLA with the team."}],
        }),
        "canvas_layout": default_canvas_layout(1, 1).model_dump(mode="json"),
    })
    _register({
        "id": "playbook-09-waiting-followup",
        "title": "Waiting on customer — internal note",
        "description": "When the ticket is waiting on the customer, log a note for the next reply.",
        "category": "operations",
        "required_capabilities": [],
        "definition": WorkflowDefinition.model_validate({
            "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
            "condition_mode": "all",
            "conditions": [{"kind": "ticket_status_is", "operator": "is", "value": "pending"}],
            "actions": [{"kind": "add_internal_note", "body": "[Automation] Ticket is waiting on the customer — follow up if silence continues."}],
        }),
        "canvas_layout": default_canvas_layout(1, 1).model_dump(mode="json"),
    })
    _register({
        "id": "playbook-10-csat",
        "title": "Resolved ticket — CSAT reminder",
        "description": "When the ticket is resolved, add an internal note to prompt CSAT or closure follow-up.",
        "category": "feedback",
        "required_capabilities": [],
        "definition": WorkflowDefinition.model_validate({
            "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
            "condition_mode": "all",
            "conditions": [{"kind": "ticket_status_is", "operator": "is", "value": "resolved"}],
            "actions": [{"kind": "add_internal_note", "body": "[Automation] Resolved — send CSAT or confirm satisfaction when your channel supports it."}],
        }),
        "canvas_layout": default_canvas_layout(1, 1).model_dump(mode="json"),
    })
    _register({
        "id": "playbook-11-shipment-exception",
        "title": "Shipment ops — Shopify connected",
        "description": "When Shopify is connected, log an internal note for fulfillment or shipment issues.",
        "category": "commerce",
        "required_capabilities": ["shopify.connected"],
        "definition": WorkflowDefinition.model_validate({
            "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
            "condition_mode": "all",
            "conditions": [{"kind": "shopify_store_connected"}],
            "actions": [{"kind": "add_internal_note", "body": "[Automation] Commerce context available — review order/shipment in Shopify if needed."}],
        }),
        "canvas_layout": default_canvas_layout(1, 1).model_dump(mode="json"),
    })
    _register({
        "id": "playbook-12-knowledge-gap",
        "title": "Knowledge gap — flag for docs",
        "description": "Catch-all path: add a note so the team can improve help content when gaps show up.",
        "category": "knowledge",
        "required_capabilities": [],
        "definition": WorkflowDefinition.model_validate({
            "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
            "condition_mode": "all",
            "conditions": [],
            "actions": [{"kind": "add_internal_note", "body": "[Automation] Possible knowledge gap — consider updating FAQs or docs."}],
        }),
        "canvas_layout": default_canvas_layout(0, 1).model_dump(mode="json"),
    })
    _register({
        "id": "playbook-13-whatsapp-adapter",
        "title": "WhatsApp conversations — route starter",
        "description": "Runs on WhatsApp when that channel is enabled; extend with your standard routing.",
        "category": "messaging",
        "required_capabilities": ["whatsapp.channel"],
        "definition": WorkflowDefinition.model_validate({
            "trigger": {"kind": "customer_message_received", "channel": "whatsapp", "first_message_only": False},
            "condition_mode": "all",
            "conditions": [],
            "actions": [{"kind": "add_internal_note", "body": "[Automation] WhatsApp message — apply your team’s routing rules from here."}],
        }),
        "canvas_layout": default_canvas_layout(0, 1).model_dump(mode="json"),
    })
    _register({
        "id": "playbook-14-commerce-refund-approval",
        "title": "Refund request — approval queue",
        "description": "When the customer mentions a refund, open a commerce approval for a human to review.",
        "category": "commerce",
        "required_capabilities": ["shopify.orders.cancel"],
        "definition": WorkflowDefinition.model_validate({
            "trigger": {"kind": "customer_message_received", "channel": None, "first_message_only": False},
            "condition_mode": "all",
            "conditions": [{"kind": "contains_keyword", "value": "refund"}],
            "actions": [
                {"kind": "request_commerce_approval", "summary": "Cancellation review", "detail": "Requires a shopper-verified order and Owner/Admin approval. No refund or order change happens automatically."},
            ],
        }),
        "canvas_layout": default_canvas_layout(1, 1).model_dump(mode="json"),
    })


_register_all()


def list_templates(
    *,
    category: str | None = None,
    available_capabilities: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for meta in _TEMPLATE_REGISTRY.values():
        if category and meta["category"] != category:
            continue
        missing: list[str] = (
            missing_capabilities(meta["required_capabilities"], available=available_capabilities)
            if available_capabilities is not None
            else []
        )
        rows.append(
            {
                "id": meta["id"],
                "title": meta["title"],
                "description": meta["description"],
                "category": meta["category"],
                "required_capabilities": meta["required_capabilities"],
                "missing_capabilities": missing,
                "available": len(missing) == 0,
            }
        )
    rows.sort(key=lambda r: (r["category"], r["title"]))
    return rows


def get_template(template_id: str) -> dict[str, Any] | None:
    return _TEMPLATE_REGISTRY.get(template_id)


def materialize_template(*, template_id: str) -> tuple[WorkflowDefinition, dict[str, Any]]:
    meta = _TEMPLATE_REGISTRY.get(template_id)
    if meta is None:
        raise ValueError("Unknown template")
    definition = meta["definition"]
    if not isinstance(definition, WorkflowDefinition):
        definition = WorkflowDefinition.model_validate(definition)
    layout = meta["canvas_layout"]
    return definition, layout
