# Phase 6 PostgreSQL Integrity Review

## Verified findings and changes

- `catalog_variants` already enforced that its product and provider connection
  belonged to the same organization, but did not require the product and
  variant to belong to the same provider connection. Migration
  `0034_catalog_variant_connection_integrity` adds the referenced composite
  unique key and the three-column foreign key. It checks for mismatched legacy
  rows first and aborts with a remediation message; it never rewrites or
  deletes catalog data. Downgrade removes only the new constraint and key.
- Catalog snapshot writes selected rows `FOR UPDATE`, then inserted if no row
  existed. A row lock cannot serialize two first inserts. Product and variant
  creation now use PostgreSQL `ON CONFLICT DO NOTHING` on the existing external
  identity constraints, then lock and update the canonical row in the same
  transaction. The product/variant unique identities and caller transaction
  are unchanged.
- Shopify order verification rows contain encrypted customer email and an OTP
  digest. They remained in PostgreSQL indefinitely after their short expiry.
  Maintenance now removes at most 100 rows per tenant per run after expiry plus
  24 hours, using transaction-local tenant context and `SKIP LOCKED`. Active,
  recently expired, and other-tenant rows are untouched. This cleanup preserves
  a short window for operational diagnosis without retaining expired OTP
  material indefinitely.

## Audited controls retained

- Tenant context uses `set_config('app.current_tenant', ..., true)`, so it is
  transaction-local and reset by commit/rollback. Request and worker sessions
  set context before tenant-owned queries.
- Existing tables with `organization_id` have matching forced-RLS policies in
  the migration history; `scripts/assert_runtime_db_role.py` checks the runtime
  database role is not superuser or `BYPASSRLS` and validates expected RLS
  policies. Existing CI provisions separate migration/runtime roles.
- Existing credential storage uses authenticated encryption in the integration
  credential service. No token, OTP, or customer secret is added to logs.
- Existing idempotency constraints remain in place for widget submissions,
  messages, provider events, and AI execution replies. Worker claim paths retain
  row locking and `SKIP LOCKED` behavior.

## Indexes and query performance

No query-performance indexes were added. PostgreSQL creates the unique backing
index required by the new composite foreign-key target; this is an integrity
constraint, not a query optimization. The environment did not provide an
isolated PostgreSQL test database, so `EXPLAIN (ANALYZE, BUFFERS)` benchmarks
could not be run. The retention cleanup is bounded and uses the existing
tenant/conversation/status/expiry index; an expiry-only index should be
considered only after measuring the real cleanup query against representative
data.

## Validation and rollback

The migration's upgrade preflight is deliberately fail-closed. To validate on a
database, first run `alembic upgrade 0033_message_connection_identity`, inspect
and reconcile any reported mismatches explicitly, then apply `alembic upgrade
head`. To roll back this migration only, run `alembic downgrade
0033_message_connection_identity`; this removes only the new FK and unique key.
No data migration is needed for downgrade.

## Remaining policy question

Widget conversations and customer messages follow existing support/audit
retention behavior and are not automatically deleted by this phase. A tenant
configurable conversation-retention policy needs product/legal requirements
before implementing deletion or anonymization.
