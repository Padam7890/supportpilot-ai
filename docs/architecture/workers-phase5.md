# Worker Runtime Phase 5

## Boundaries

`app/workers/application/dispatcher.py` fairly rotates approved organizations and job families. The handler adapters in `app/workers/handlers/` delegate work to the existing AI, catalog, knowledge ingestion, commerce, and outbound delivery services. `app/workers/infrastructure/job_repository.py` owns approved-tenant iteration and tenant-scoped failed-job counts. Retry delays live in `app/workers/domain/retry_policy.py`; `app/workers/runtime.py` owns bounded worker slots and graceful signal shutdown. `app/worker.py` remains a compatibility entry point for ingestion helpers and the CLI.

Claims remain in each job family so each claim transaction can set transaction-local tenant context, use its existing constraints and `FOR UPDATE SKIP LOCKED`, persist the running state, and commit before work begins. There is no new queue technology or shared jobs table.

## Durable job families and terminal failures

| Handler | Existing durable record | Retry / terminal state |
| --- | --- | --- |
| AI execution | `ai_executions` | bounded attempts; safe failure status |
| Catalog sync / webhook | `catalog_sync_jobs`, `catalog_webhook_events` | persisted attempts and provider error codes |
| Document ingestion | `document_ingestion_jobs` | bounded attempts; failed rows retained for history |
| Commerce action | `commerce_actions` | approved actions only; ambiguous Shopify mutations fail closed |
| Outbound delivery | `integration_delivery_jobs` | transactional outbox, stable job idempotency key, retry-after support |

The outbound delivery row is inserted with the message in its transaction and remains the transactional outbox. Incoming integration events retain their current idempotency/outbox implementation. Failed states remain queryable in the existing feature APIs/database; the dispatcher emits per-tenant failed-job counts at most every 15 minutes without logging message bodies or credentials.

## Scheduling, limits, and shutdown

The dispatcher rotates both tenant position and the next handler family, so a continuously busy AI queue does not permanently precede ingestion, commerce, or outbound delivery. Handler processing has an outer timeout configured by `WORKER_JOB_TIMEOUT_SECONDS` (default 110 seconds); the runtime creates a bounded number of worker loops from `WORKER_CONCURRENCY` (default 4, maximum 32). These defaults keep the processing timeout below the shortest current three-minute lease. Feature-level provider timeouts and retry behavior remain in force.

Retryable provider/document failures use capped exponential full jitter. Shopify commerce mutations are not automatically retried after ambiguous outcomes; this preserves the existing fail-closed behavior. A process crash leaves its committed job in `running`; a later claim can reclaim it only after the existing lease expires. Stable outbound idempotency keys protect redelivery. `SIGINT`/`SIGTERM` stops new claims and waits for in-flight handlers to finish within their job timeout.

## Database and rollback

This phase adds no schema changes. Rollback consists of restoring the previous worker entry point and service imports; persisted rows and status contracts are unchanged. Because claims and leases remain feature-local, operations must continue using the restricted runtime database role with RLS enabled. PostgreSQL integration checks remain necessary before deployment.

## Operational signals

Structured worker logs include job family, tenant ID, durable job ID when present, elapsed time, timeout, safe error type, concurrency configuration, and failed-state counts. They deliberately omit payloads, customer messages, and credentials. Alerts should track repeated `worker_job_timeout`, `worker_claim_failed`, `worker_job_unhandled_error`, and nonzero `worker_dead_letter_counts` events.
