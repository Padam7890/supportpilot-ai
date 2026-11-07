# Automation playbook — implementation roadmap (post–Phase 2)

This document captures **planned** contracts and infrastructure for phases **3–5** and **WorkflowDefinition v2** branching. The runtime today remains **linear** (`conditions` → `actions`) with **`customer_message_received`** as the only publishable trigger.

## Phase 3 — Scheduler and timers (non-message triggers)

**Planned trigger kinds** (not in the API schema until enqueue exists):

- `sla_deadline` — first-response or resolution SLA windows.
- `waiting_for_customer_timeout` — nudges while ticket status is waiting.
- `knowledge_index_failed` — knowledge pipeline health.

**Infrastructure**

- Durable jobs with `run_at` / lease renewal, or a dedicated `automation_timer` job kind.
- Persist **wait state** (correlation id, deadline, ticket snapshot hash) on `AutomationExecution` or a sibling table.
- New enqueue producers: ticket lifecycle hooks, bounded cron ticks, knowledge job failures.

**Policy**

- Re-read live ticket/conversation state immediately before side effects to avoid stale closes.

## Phase 4 — Channels and normalized adapters

**Planned**

- `adapter_inbound_normalized` trigger with a shared envelope: `event_type`, `workspace_id`, `correlation_id`, `dedupe_key`.
- Capability matrix per channel (WhatsApp, Messenger, etc.) aligned with `organization_capabilities`.
- Marketplace templates gated on `whatsapp.channel` / `messenger.channel`.

## Phase 5 — Commerce writes and replay protection

**Current**

- `request_commerce_approval` creates a **pending** `CommerceAction` (Shopify cancel placeholder) plus a **system** conversation note — **no provider write** until human approval through existing commerce flows.

**Planned**

- Tie automation-generated requests to **verified order numbers** before execution queues.
- Re-fetch order state at approval time; strict idempotency on provider calls (reuse `CommerceAction` idempotency patterns).

## WorkflowDefinition v2 — branching graph

**Current**

- Single linear path after trigger: all/any conditions, then ordered actions.

**Planned migration**

- Internal graph: nodes + edges with **True/False** or **success/failure/timeout** ports.
- Version **WorkflowDefinition** in JSON; migrate published rows with a Alembic data migration (similar to canvas layout `0041`).
- **Dry-run / preview**: simulate branch outcomes with redacted payloads.
- UI: branching canvas; keep linear definitions working until migration flag flips.
