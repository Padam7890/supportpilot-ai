# Omnichannel integrations: current architecture and staged migration

## Current state inspected

The application is FastAPI with asynchronous SQLAlchemy, Alembic, PostgreSQL row-level security, and a Next.js BFF. API routes are collected in `backend/app/api/router.py`; integration work currently lives mainly in `backend/app/api/routes/integrations.py` and `backend/app/api/routes/widgets.py`.

- Shopify is a tenant-scoped commerce integration. `ShopifyInstallation` stores the shop identity, encrypted access/refresh tokens, granted scopes, expiry, and connection actor. `ShopifyOAuthState` is single-use and tenant/user scoped. Provider code now lives in `app/integrations/providers/shopify/`: `client.py` performs GraphQL/OAuth requests and redacts credentials from structured logs; `orders.py` authorizes order lookup; `security.py` owns Shopify OAuth and credential crypto; `actions.py` owns Shopify order-action calls. Existing `/integrations/shopify/*` routes still coordinate OAuth and responses, so the HTTP layer retains some provider orchestration.
- The core domain already has one `Conversation` and `Message` model. A conversation has a free-form channel name and tenant/ticket foreign keys. Messages have sender identity and private-note support, but no provider connection, external message ID, outbound delivery state, or provider-scoped external conversation ID.
- The Shopify storefront widget creates/continues conversations through authenticated visitor-session endpoints. It is a first-party web channel, not a third-party provider webhook.
- There is no generic webhook receiver, event inbox, message dispatcher, or integration registry today. Shopify API calls are request/worker initiated rather than driven by a webhook ingestion pipeline.
- `backend/app/worker.py` polls PostgreSQL job tables for knowledge ingestion, AI executions, and commerce actions using row locks and leases. Redis is used for rate limiting and is not currently the durable work queue. Reuse this database-backed job pattern for provider events and outbound delivery; do not add BullMQ or a second queue system.
- Tenant isolation is based on explicit organization filters plus forced RLS and transaction-local `app.current_tenant`. New tenant tables must use the same policy and must be included in the runtime-role/RLS verifier.
- Frontend integration management is presently a Shopify card and storefront-widget settings card. There is no generic integrations catalog or connection detail/log UI.

## Target design

Use Python protocols and domain DTOs, matching the actual backend language. Protocols are capability based so a commerce connector does not have to implement messaging methods. Provider SDK types and HTTP details stay inside provider adapters.

```text
FastAPI route / verified provider webhook
                |
     integration application service
       /                    \
provider registry       durable event/job store
       |                    |
provider adapter <--- worker/outbound dispatcher
       |
normalized domain DTOs -> ConversationService -> Message/AI/handoff
```

The core package should provide:

- Provider metadata and capability protocols (`commerce`, `messaging`, `sync`, `webhooks`).
- A startup-populated registry that rejects duplicate provider IDs, resolves a provider, and checks capabilities. Registry entries are concrete adapters only; no empty WhatsApp/Meta/Email placeholders.
- Normalized inbound message, outbound message, delivery result, webhook event, and sync cursor DTOs using Python types and Pydantic validation at external boundaries.
- Provider-neutral integration errors that preserve safe categories and retryability without including credentials or raw PII.
- Application services for accepting events, resolving connections, mapping external identities, and dispatching sends. Existing conversation logic remains provider independent.

The populated Python package is organized by responsibility:

```text
app/integrations/
  core/
    contracts/       # normalized DTOs and provider metadata
    interfaces/      # provider and capability protocols
    registry/        # duplicate-safe adapter lookup
    errors/          # safe provider-neutral failures
    types.py         # shared capability enum/types
  providers/shopify/ # concrete Shopify API, OAuth, order, and action code
  connections/      # tenant connection lifecycle and synchronization
  credentials/      # encrypted credential-record persistence
```

Only directories with working code are created. Webhook, sync, events, queues, mapper, and monitoring packages will be added alongside their first concrete implementation rather than as empty placeholders. The `app.integrations.core` package exports the stable contracts/registry surface. Deprecated `app.services.shopify_*` and `app.services.integration_connections` re-export shims are retained for one transition release; application code and tests use the new paths.

Shopify will be registered as a commerce adapter and will delegate to the existing secure client/order services. It will not claim messaging support. The storefront widget will use the normalized incoming-message application service directly; it will not be forced through a fake webhook adapter. Existing Shopify routes remain compatible and become thin delegates as each endpoint is migrated.

## Data and migration strategy

Additive changes only; do not drop or rewrite existing Shopify data in the first migration.

1. Add `integration_connections` with tenant ID, provider key, external account ID, display name, lifecycle/health state, timestamps, and safe provider configuration. Unique constraints cover `(organization_id, provider_key, external_account_id)` and indexes cover tenant/status/provider lookup.
2. Add `integration_credentials` owned by a connection, with credential type, encrypted value, key version, expiry, rotation metadata, and timestamps. The encrypted value must use authenticated encryption and never be returned by an API. First migrate the currently encrypted Shopify token values byte-for-byte; decryption compatibility must be verified before enabling generic writes. Continue using the existing encryption key during the compatibility period; key rotation/re-encryption is a separate explicit operation.
3. Add nullable `integration_connection_id` and `external_conversation_id` to `conversations`, and nullable `external_message_id`, delivery status, and safe provider metadata to `messages`. Backfill the existing Shopify-widget channel as a first-party source without assigning it a fabricated external provider connection. Provider-scoped uniqueness is enforced only when an external ID is present.
4. Add `integration_webhook_events` for verified, durable event acceptance, deduplication key, safe payload storage, timestamps, attempts, and terminal status. Raw provider bodies may contain PII: encrypt or minimize them, enforce retention, and never print them in logs. Add connection-scoped `integration_sync_jobs` and `integration_delivery_jobs` only when those flows are implemented; their states and retry scheduling must be explicit.
5. Apply organization RLS to every tenant-owned table and add composite foreign keys tying connection, conversation, and event rows to the same organization. Include all tables in the CI policy inventory and test cross-tenant rejection.
6. Deploy in expand/backfill/verify order. Preserve ShopifyInstallation as the compatibility source while a migration/adapter dual-reads it and new Shopify connections write both models. Compare row counts and decrypt a sample in a controlled test. Only a later migration may retire the old table after all routes and workers use the generic store. Rollback before that point is application rollback; the additive schema remains safe.

## Delivery phases

1. **Architecture and contracts:** this document; typed capability protocols, normalized DTOs, registry, and provider-neutral error types. Do not register a provider until its adapter is concrete; register Shopify during its cutover after it delegates to the existing secure client and connection service.
2. **Connection foundation:** additive tenant-scoped connection/credential tables, migration/backfill, service layer, and protected connection list/detail/disconnect APIs. Preserve Shopify endpoints during cutover.
3. **Shopify adapter cutover:** route Shopify read operations through the commerce capability and generic connection resolver; keep OAuth validation, token refresh, scopes, tenant checks, and existing API responses unchanged.
4. **Unified messaging:** normalization service for the existing storefront widget, external ID idempotency fields, inbound event persistence, and outbound dispatch state. Keep human/AI policy and conversation/ticket behavior in existing domain services.
5. **Webhook foundation:** provider-specific raw-body signature verifiers, challenge hooks where required, durable accept/ack, dedupe, leased processing, bounded retries with jitter, and terminal failed-event inspection. Implement a real provider's webhook only alongside its actual account/auth setup.
6. **Delivery and sync:** durable outbound delivery and cursor-based sync jobs, retry classification, provider/tenant rate limits, reconnect/health transitions, and operator-facing failure details.
7. **Hardening:** cross-tenant, replay, duplicate, out-of-order, retry/dead-letter, token refresh, disconnection, and AI/human takeover tests; docs for setup, metrics, key rotation, deployment, retention, and rollback.

Each phase must pass backend lint, API contract generation/drift, PostgreSQL integration/RLS tests, and relevant mocked provider tests. Browser tests are added when the corresponding connection-management UI is introduced. A future provider is not called functional until its authentication, real API adapter, signature verification, and tests exist.

## Risks and boundaries

- Existing Shopify installation uniqueness permits one shop per tenant. The generic model can support multiple accounts, but the old OAuth callback and UI remain single-store until explicitly migrated and tested.
- Existing `Message` creation and AI queueing happen in application code. The normalization service must call that same business path so incoming messages do not bypass AI mode, idempotency, or agent takeover checks.
- Webhook acknowledgement must occur after durable insert, but provider-specific verification and connection resolution happen before acceptance. Out-of-order events need provider timestamps/sequences where available; otherwise the system must avoid claiming strict ordering.
- Credential encryption currently depends on `SHOPIFY_ENCRYPTION_KEY`. Do not rename/remove it until all encrypted credentials have a tested re-encryption path and a documented rollback window.
- Retain limited safe operational metadata, not full unredacted payloads. Apply tenant-scoped inspection permissions and retention limits before exposing event logs.
- This product plan does not provision AWS or other cloud resources. Deployment-specific secret managers, queue workers, alerting, and storage are tracked as infrastructure dependencies.

## Implementation status (2026-11-01)

The current working tree has implemented the first additive slices; later phases remain open until their integration and database tests run against PostgreSQL.

- **Architecture/contracts:** provider-neutral errors, validated message/webhook DTOs, capability protocols, and duplicate/capability-safe registry are split into focused `core/contracts`, `core/interfaces`, `core/types.py`, `core/registry`, and `core/errors` modules. `app.integrations.core` retains stable top-level exports. No nonfunctional channel adapters are advertised.
- **Package migration:** Shopify API, order, security, and action modules live under `providers/shopify`; generic connection lifecycle and credential-row persistence live under `connections` and `credentials`. Old service import paths are compatibility shims for one transition release.
- **Connection foundation:** migrations `0023_integration_connections` and `0024_normalized_messages` add tenant-scoped connections/credentials and provider identity/delivery fields. Existing Shopify records and ciphertext are copied additively. Shopify connect, refresh, and disconnect paths dual-write generic connection state. Authenticated provider/connection list/detail/disconnect APIs return safe metadata only; Shopify disconnect clears both stores' ciphertext.
- **Messaging foundation:** conversation and message models now reserve provider-scoped external IDs, delivery state, and safe metadata. Existing storefront widget behavior is preserved. The third-party webhook event table, verified webhook receiver, normalized message application service, and outbound dispatcher are not implemented yet.
- **Shopify cutover:** existing Shopify OAuth, token refresh, status, order listing, and verified order lookup still use the legacy installation path. The generic registry deliberately does not yet advertise Shopify because the adapter/token lifecycle has not been cut over and exercised end to end.
- **Admin UI and operations:** generic connection management UI, health/event log views, durable provider webhook jobs, metrics, and retry/dead-letter handling remain open.

Validation performed locally without Docker: Alembic rendered migrations `0001`–`0024` to offline SQL; API OpenAPI export and generated TypeScript type drift check passed; backend Ruff and pytest passed for available tests; frontend lint, typecheck, and Vitest passed. PostgreSQL-backed tests are still skipped when `TEST_DATABASE_URL` is absent, so this does not verify a live migration, RLS policies, or tenant foreign-key rejection. Playwright could not run because the Playwright Chromium executable is not installed in this environment.
