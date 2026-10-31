# SupportPilot UI Roadmap

This roadmap tracks product screens separately from infrastructure delivery. A phase stays **in progress** until its listed tests have run successfully against the intended dependencies.

## Delivery status

| Phase | Scope | Status | Gate |
| --- | --- | --- | --- |
| Sprint 3 | Approval gate, shared UI foundation, inbox | In progress | PostgreSQL integration and Playwright workflows must run in CI. |
| Sprint 4 | Knowledge documents and durable ingestion | Not started | Job retries, reprocessing, search, citations, tenant tests. |
| Sprint 5 | AI playground and grounded reply drafts | Not started | Persisted checkpoints, safe summaries, draft-only sending. |
| Sprint 6 | Mock commerce and action approvals | Not started | Idempotent transactional state transitions and audit history. |
| Sprint 7 | Analytics and evaluation | Not started | Real aggregate APIs and bounded time-series queries. |
| Sprint 8 | Security and operational status | Not started | Tenant-scoped settings and dependency health APIs. |
| Sprints 9–10 | Public pages, search, notifications | Not started | No capability or metric appears without a supporting API. |

## Acceptance gates for every phase

- **Accessibility:** keyboard-only navigation, visible focus, labeled controls, reduced-motion behavior, and automated axe checks on primary workflows.
- **Performance:** bounded API pages and uploads, query/index review, and no unbounded polling or background work.
- **Contracts:** OpenAPI contract tests, generated TypeScript drift checks, and consistent RFC 9457 errors.
- **Isolation:** role checks and PostgreSQL tenant-isolation tests for every organization-owned read and write.
- **Completion:** lint, type checks, unit/integration tests, migrations, and the phase’s Playwright paths run successfully before its status changes.

## Phase acceptance criteria

### Sprint 3 — Approval, foundation, inbox

- A new registration receives no session; pending and rejected organizations cannot log in; approval enables only the tenant workspace session.
- Platform-owner authentication and cookies remain separate from tenant authentication and cookies.
- Inbox rows are ticket-centered and use server-side filters, signed keyset cursors ordered by `updated_at DESC, ticket_id DESC`, and the generated snake_case wire contract.
- If a ticket has multiple conversations, the UI requires a conversation choice before loading its transcript.
- Unread count means customer messages after the current user’s read cursor across that ticket’s conversations. Opening a conversation advances only its cursor.
- CI migrates with the migrator role, then runs API tests as the restricted runtime role and executes the approval/login Playwright paths.

### Sprint 4 — Knowledge

- Authorized users can upload, list, inspect, search, reprocess, and remove tenant-owned documents.
- Durable jobs expose queued/running/succeeded/failed states, bounded retries, and retained job history; temporary processing artifacts are cleaned up.
- Search results include stable document and chunk citations; failures and empty states are visible and retryable.

### Sprint 5 — AI assistance

- The playground and inbox may show grounded drafts with citations, but an agent must explicitly send a draft.
- Execution checkpoints persist across restarts. APIs expose status, sources, tool outcomes, and usage only; private reasoning, credentials, and sensitive tool arguments are never returned.
- TanStack Query polling pauses while the page is hidden. Streaming and WebSockets are outside the MVP.

### Sprint 6 — Operations

- Order lookup uses the planned mock commerce service and tenant-scoped access.
- Refund/cancellation approval and execution state machines are independent, auditable, idempotent, and transaction-safe.
- Agents may request actions, Owners/Admins may approve, and Viewers remain read-only.

### Sprint 7 — Insights

- Support, AI usage/cost, and evaluation views use bounded aggregate APIs, with date-range validation and tenant isolation.
- Empty, loading, error, and no-data states are present; no sample metrics are shown as live data.

### Sprint 8 — Administration

- Security settings and operational status are backed by explicit APIs, with Owner/Admin write permissions and read-only role behavior.
- Platform-owner tooling stays under `/platform/*` and cannot access tenant sessions.

### Sprints 9–10 — Public pages and team productivity

- Landing, features, and pricing pages describe only implemented capabilities and approved pricing content.
- Tenant-scoped command search and notifications ship only with supporting, permission-checked APIs and bounded results.

## Infrastructure dependencies (tracked separately)

| Product phase | Infrastructure dependency | This roadmap includes |
| --- | --- | --- |
| Sprint 3 | Local Compose PostgreSQL, Redis, CI service containers | Local/test configuration and verification only |
| Sprint 4 | Durable worker runtime and persistent document storage | Product/API dependency tracking; no cloud provisioning |
| Sprint 5 | Configured model provider and checkpoint storage | Safe integration contracts; no provider secrets or deployment |
| Sprint 6 | Mock commerce service | Product workflow and state/audit behavior |
| Sprints 7–10 | Production observability and deployment services as needed | Dependencies only; AWS implementation/provisioning excluded |
