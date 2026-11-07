# Automation Foundation — Initial Release

## Scope

Automation is a constrained, tenant-scoped rule engine on the existing PostgreSQL-backed worker. The message trigger supports up to five `contains_keyword` conditions and up to ten allowlisted actions: ticket priority/status and assignee updates, conversation AI mode, internal notes, read-only verified Shopify order lookup, Shopify catalog search, and a shopper-verified cancellation review request. Workflow configuration is Owner/Admin-only. Agents and Viewers can inspect workflows and execution history.

No arbitrary code, SQL, external HTTP requests, Shopify mutations, outbound message sends, or model-generated actions are accepted. A cancellation review can be created only for the active, OTP-verified Shopify order in the same widget conversation. The workflow records a pending commerce action for Owner/Admin review; it never cancels the order, issues a refund, restocks, or notifies the shopper. Non-widget conversations without a matching active verification are safely skipped. Refund review is not an automation action.

## Persistence and execution

- `automation_workflows` stores the editable definition, visual draft layout, and active/paused state.
- `automation_workflow_versions` stores immutable published definitions and their visual layouts.
- `automation_executions` is the durable queue, execution history, and dead-letter record. Its unique `(organization_id, workflow_id, event_key)` constraint prevents duplicate runs for one inbound message.
- Widget and configured integration inbound-message paths enqueue matching published workflows in the same transaction that persists the message. Retries of the same message cannot enqueue another execution.
- The dispatcher leases work with `FOR UPDATE SKIP LOCKED`, uses a two-minute lease and at most three attempts, and applies bounded exponential retry delay with jitter. Each lease carries a fencing token, so a worker whose lease was replaced cannot apply changes or overwrite the newer attempt. Ticket updates and execution success commit atomically. Expired leases recover after worker interruption.
- The worker revalidates assignment targets as active, same-tenant support members. Ticket actions create a `ticket_activities` audit entry containing only before/after values.
- Correlation IDs are validated at the API boundary, returned as `X-Correlation-ID`, and propagated to automation executions and worker logs. Logs include route templates, status, duration, organization/job identifiers, and error class, but not message content, email, tokens, or provider payloads.

## API

- `GET/POST /api/v1/automations`
- `GET/PATCH /api/v1/automations/{workflow_id}`
- `POST /api/v1/automations/{workflow_id}/publish`
- `POST /api/v1/automations/{workflow_id}/pause`
- `POST /api/v1/automations/{workflow_id}/resume`
- `GET /api/v1/automations/{workflow_id}/executions`
- `GET /api/v1/automations/metrics?days=30` (1–90 days)

All reads and writes are tenant-scoped and backed by forced RLS and composite tenant foreign keys. History is bounded to the most recent 100 workflow executions per request. Metrics aggregate only persisted executions for the caller’s organization.

## Rollout

1. Apply additive migration `0038_automation_foundation` as the migrator role.
2. Apply additive migration `0041_automation_canvas_layout` as the migrator role. Legacy rows remain valid; the API calculates deterministic default positions until a draft is saved.
3. Deploy the API and worker together so queued work has a handler.
4. Create a workflow in draft, publish it, send a storefront test message, then inspect its execution and ticket activity.
5. Pause stops new executions; already-queued runs remain tied to their immutable published version and can finish.
6. Migration downgrade intentionally refuses to drop non-empty automation history or saved canvas layouts. Roll back application code while preserving the additive tables; archive/export data before any separately reviewed schema removal.

## Current limitations

The dashboard offers an accessible movable canvas for a constrained linear rule rather than a general graph editor. Node layout is presentation metadata; workflow evaluation remains customer-message trigger → keyword conditions (AND) → one allowlisted action. Only one action can be attached to a workflow in this release. Approval steps, team routing, arbitrary branches, scheduled triggers, and external side effects remain unavailable. PostgreSQL migration, RLS, worker crash/retry, and end-to-end acceptance must be run before this capability is marked production-ready.
