# SupportPilot UI Roadmap

This roadmap tracks product screens separately from infrastructure delivery. A phase stays **in progress** until its listed tests have run successfully against the intended dependencies.

## Delivery status

| Phase | Scope | Status | Gate |
| --- | --- | --- | --- |
| Sprint 3 | Approval gate, shared UI foundation, inbox | In progress | PostgreSQL integration and Playwright workflows must run in CI. |
| Sprint 4 | Knowledge documents and durable ingestion | In progress | PostgreSQL integration and knowledge Playwright flow must pass. |
| Sprint 5 | AI playground and grounded reply drafts | In progress | Persisted checkpoints, safe summaries, draft-only sending, PostgreSQL integration, and browser workflows. |
| Sprint 6 | Shopify read-only integration and human-reviewed operations | In progress | Tenant-scoped OAuth, encrypted rotating credentials, verified order lookup, audit, and browser workflows. Refund/cancellation requests use separate approval and execution states with a mock executor; Shopify writes stay disabled. |
| Sprint 7 | Analytics and evaluation | In progress | Ticket and AI usage aggregates, configurable cost estimates, and teammate feedback API/UI are present; PostgreSQL and browser gates must pass. |
| Sprint 8 | Security and operational status | In progress | Per-user session management and a readiness details page are present; browser, migration, and PostgreSQL access-boundary gates remain. |
| Sprint 9 | Public landing, features, pricing | In progress | Pages describe shipped behavior and omit unpublished prices; browser/accessibility tests must pass. |
| Sprint 10 | Command search and notifications | In progress | Tenant-scoped command search API and keyboard-accessible UI are present; notifications remain absent until a permission-checked notification source/API is defined. |

## Live sprint tracker

Last verified: **2026-10-31**. Sprints 3–10 have implementation work in place but remain open until their PostgreSQL and browser acceptance gates run successfully. Local database containers were not restarted for tests; the API container was restarted once to reload the confirmed Shopify store domain.

| Sprint | Implementation evidence | Verification evidence | Remaining work / gate |
| --- | --- | --- | --- |
| Sprint 3 | Shared light-default/dark design tokens, accessible primitives, and global reduced-motion handling are present. Tenant approval flow, isolated platform sessions, inbox filters/read state, responsive ticket/customer context, private internal notes, Owner/Admin assignment management and self-claim, agent self-claim for unassigned tickets, customer message history, explicit multi-conversation selection, activity timeline, and CI database/E2E jobs are present. CI asserts the API role cannot bypass RLS, checks both `USING` and `WITH CHECK` predicates against the active tenant setting, and dynamically checks every `organization_id` table against the tenant-policy inventory, including later analytics and integration tables. Browser axe scans include platform approvals, Operations, Security, Settings, ticket detail, and Inbox desktop/mobile flows. CI runs frontend unit tests, validates the Compose graph, generates a disposable Fernet key for its Shopify test environment, and retains Playwright failure artifacts. | Latest local backend run: 41 passed, 21 skipped; the skipped tests require isolated PostgreSQL/pgvector or unavailable optional dependencies. The CI role-provisioning script was exercised against a disposable local PostgreSQL cluster; runtime `NOBYPASSRLS` and migrator `BYPASSRLS` flags and quoted passwords were verified. Ruff and OpenAPI drift checks pass. Frontend lint, TypeScript, 22 unit tests, and generated API type drift pass. The Playwright accessibility run was attempted but Next.js could not bind to loopback port 3000 (`EPERM`). The latest GitHub Actions run failed during checkout in backend and E2E jobs because a PostgreSQL init-script bind mount created a root-owned workspace directory. The workflow now removes that mount and provisions roles after checkout; it still needs a successful CI run. | Push the checkout fix and verify PostgreSQL-backed approval/session/inbox/RLS and approval/login Playwright runs in CI. |
| Sprint 4 | Tenant-scoped document upload/search, durable ingestion jobs with bounded retries/reprocessing, and a knowledge UI are present. Reprocess locks the document and rejects duplicate requests while an ingestion job is queued or running. Removed documents keep tombstone metadata and job history while source bytes and searchable chunks are deleted; queued/running jobs are cancelled. The worker locks document/job rows in a consistent order and rechecks removal before publishing chunks, preventing deleted content from being resurrected. The E2E workflow covers upload, search citations, document detail/history, reprocessing, and removal, with axe scans on library and detail pages. | Backend Ruff passes; current local suite is 32 passed and 17 PostgreSQL/dependency tests are skipped. The knowledge ingestion/search/reprocess integration tests pass against fresh isolated PostgreSQL; Alembic SQL renders through `0014_read_only_migration_ledger`. Frontend lint, typecheck, 20 unit tests, and OpenAPI drift pass. Five browser tests are discoverable but were not run. | Run PostgreSQL-backed ingestion/deletion/retry and tenant-isolation tests plus the full document lifecycle browser flow against isolated PostgreSQL in CI. |
| Sprint 5 | Tenant-scoped queued AI executions, a configurable server-side OpenAI-compatible gateway, LangGraph PostgreSQL checkpoints with tenant RLS, knowledge-grounded citations, safe execution summaries, an AI playground, and inbox draft insertion are present. Tenant active-job limits are serialized on the organization row so concurrent enqueues cannot exceed capacity. Drafts remain unsent until an agent explicitly sends them. | Fresh isolated PostgreSQL verification passed checkpoint persistence, grounded retrieval, tenant isolation, and concurrent execution-limit tests. The inbox/playground browser workflows were discovered but not run. | Run PostgreSQL-backed checkpoint/RLS/concurrency tests and browser workflows in CI with a mock provider. Verify expiry/retention expectations for stored executions before phase completion. |
| Sprint 6 | The read-only Shopify connector has per-tenant authorization-code OAuth for production and a development-only configured-store client-credentials path, encrypted token persistence, renewal, exact order-number/customer-email verification, access audit, and Owner/Admin connection settings. The confirmed store domain is `supportpilot-demo-stor.myshopify.com`; storefront password does not control Admin API authentication. Human-reviewed refund/cancellation requests use separate approval and execution states, idempotency keys, audit history, and a bounded durable mock worker; Shopify writes remain disabled. | A fresh client-credentials token exchange returned HTTP 200. Its response had an empty `scope`; the follow-up `currentAppInstallation.accessScopes` query also returned an empty list, confirming the store’s current app installation has no granted scopes. The connector now falls back to that GraphQL query when token scope metadata is empty, but still rejects access unless `read_orders` and `read_customers` are actually granted. Backend Ruff passes and Shopify unit tests pass (8 passed, 1 skipped). Migration `0015_commerce_actions` is applied to the local database, and `/health/ready` returns HTTP 200. The API process was not restarted, so the running app has not loaded the latest source changes. PostgreSQL commerce integration and Shopify/browser workflows remain unrun. | Release/update the Shopify app version and approve/install the required read scopes, then reconnect and verify order/customer access. Restart the API when ready to load the new scope-check/logging code. Run PostgreSQL state-transition/idempotency/tenant-isolation tests and Shopify/approval Playwright flows in CI. Keep the mock executor as the only operation backend until a separate plan enables Shopify writes. |
| Sprint 7 | Tenant-scoped AI usage aggregates with a trailing 30-day default, validated date ranges capped at 366 days, daily token series, optional estimates from explicitly configured input/output token prices, and teammate ratings for successful reply drafts are present. The Analytics screen shows loading/error/empty states, date controls, usage, estimates, and a feedback form. No provider price is assumed. | Backend unit tests cover date windows; fresh isolated PostgreSQL integration passed aggregate isolation and evaluation upsert. Frontend unit coverage exercises the usage and feedback view. OpenAPI types and migration SQL through `0014_read_only_migration_ledger` are current. Browser accessibility path is added but not run. | Run the PostgreSQL aggregate/role/isolation tests and Playwright analytics/accessibility flow in CI; production build passes after the deterministic footer-year fix. |
| Sprint 8 | `/auth/sessions` lists the current user's unexpired, unrevoked refresh sessions with bounded pagination; `DELETE /auth/sessions/{id}` revokes only a session owned by that same user and tenant. Added persisted session creation timestamps. The Security page now exposes next/previous pagination and a visible range for the bounded session list. The Operations page displays the database/Redis readiness API with refresh, loading, error, and last-checked states; API readiness now fails with an actionable migration-drift error when Alembic is behind. It explicitly does not claim worker/provider health that is not measured. | Backend suite ran on fresh isolated PostgreSQL, including session ownership checks; OpenAPI generation, frontend lint/typecheck/20 unit tests, and migration SQL rendering pass. The E2E Security/Operations flow was not run locally. | Run migration and session cross-user/tenant tests plus Operations/Security Playwright and axe checks in CI. The stale-migration readiness message has a local component regression test. Revisit immediate access-token invalidation if the product requires revocation to terminate sessions before the short access-token expiry. |
| Sprint 9 | Responsive public landing, features, and pricing pages are present. Capability descriptions match current inbox, document, human-reviewed AI draft, tenant approval, and read-only Shopify behavior. Pricing explicitly states that rates and plan limits are not published; it invents no prices, usage caps, or contact address. | Frontend lint, typecheck, and 20 unit tests pass. Five browser tests, including authentication and page-level axe coverage, are discovered but were not run locally. Production build passes after the deterministic footer-year fix. | Run the public-page Playwright and accessibility flow in CI, then review final content before marking complete. |
| Sprint 10 | Added tenant-scoped `/search` across tickets, customers, and active knowledge documents; results are ordered deterministically, limited to five per kind by default and ten maximum. Dashboard command palette supports Ctrl/⌘+K, visible search button, keyboard focus return/trapping, Escape, loading/error/empty states, and direct links. Notifications are intentionally not shown because no notification event source/API exists. | Backend search/tenant-isolation integration tests passed against fresh isolated PostgreSQL; frontend shortcut/result unit coverage passes. Command-search E2E coverage is discoverable but was not run locally. | Run PostgreSQL search/isolation and Playwright keyboard/accessibility checks in CI. Define a real notification source and read-state contract before building notification UI. |

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
- Inbox provides a desktop ticket/thread/customer-context workspace and a mobile single-panel flow. Integration and browser tests must verify ticket updates, assignment permissions, customer history, activity, keyboard behavior, and responsive states.
- Agents can claim unassigned tickets; only Owners/Admins can change assignment to another teammate. Ticket detail requires an explicit choice when multiple conversations exist.
- Internal notes are visible to workspace teammates, use a separate API, and are excluded from customer message history, public message responses, unread counts, and AI prompt context.
- Customer profiles show a bounded recent message history across tickets and conversations, with internal notes omitted.
- The inbox composer sends a public reply or a private teammate note, and the activity timeline records ticket status, priority, and assignment changes.
- CI migrates with the migrator role, verifies runtime-role privileges and forced tenant RLS, then runs API tests as the restricted role and executes the approval/login Playwright paths.

### Sprint 4 — Knowledge

- Authorized users can upload, list, inspect, search, reprocess, and remove tenant-owned documents.
- Durable jobs expose queued/running/succeeded/failed/cancelled states, bounded retries, reprocessing, and retained job history. Removing a document deletes source bytes and indexed passages while retaining a document tombstone and its job audit records; active jobs are cancelled safely.
- Search results include stable document and chunk citations; failures and empty states are visible and retryable.

### Sprint 5 — AI assistance

- The playground and inbox may show grounded drafts with citations, but an agent must explicitly send a draft.
- Execution checkpoints persist across restarts. APIs expose status, sources, tool outcomes, and usage only; private reasoning, credentials, and sensitive tool arguments are never returned.
- Execution requests are tenant-scoped, bounded, retry-limited, and polled only while the page is visible. Provider secrets remain server-side and the feature stays unavailable until the provider endpoint/model are configured.
- TanStack Query polling pauses while the page is hidden. Streaming and WebSockets are outside the MVP.

### Sprint 6 — Operations

- Production Shopify connections are tenant-scoped and use the supported standalone OAuth authorization-code flow, one-time state, callback HMAC validation, and rotating expiring offline credentials encrypted at rest. A development-only configured-store client-credentials grant avoids the browser authorization redirect for a preinstalled app/store in the same Shopify organization.
- Only `read_orders` and `read_customers` are requested. API versions are explicit and configurable; order lookup uses the GraphQL Admin API.
- An order number alone never releases customer order history. Lookup requires an exact order-number and customer-email match; access attempts are audited without storing the email in the audit record.
- Only Owners/Admins can connect or disconnect the store. Agents can perform verified read-only order lookup; Viewers cannot access order data.
- Refund/cancellation requests use separate approval (`pending`, `approved`, `rejected`, `expired`, `cancelled`) and execution (`not_started`, `queued`, `running`, `succeeded`, `failed`) states, idempotency keys, transaction-safe row locks, role checks, and immutable audit events. Execution currently uses a deterministic mock commerce service and never changes Shopify orders. Any live Shopify execution requires an explicitly planned scope, approval, and test phase.

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
| Sprint 6 | Shopify development store, app credentials, callback URL, and protected customer-data approvals | Connector and local configuration only; no Shopify resources are provisioned by the roadmap |
| Sprints 7–10 | Production observability and deployment services as needed | Dependencies only; AWS implementation/provisioning excluded |
