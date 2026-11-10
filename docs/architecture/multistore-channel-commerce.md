# Multi-store, multi-channel commerce architecture

## Current incremental implementation
- `catalog_discovery.py` lists products from a single connected provider account and tenant, not from RAG.
- Widget browse requests resolve a server-owned conversation integration connection. If absent, a singleton connection is accepted; multiple connections fail closed.
- Text results are transport-neutral. No native WhatsApp/Messenger cards, WooCommerce connector or live Shopify refresh is implemented.
- Catalog sync correctness and storefront publication eligibility still require verification.

## Target architecture (not yet implemented)
1. Add tenant-scoped `stores` with provider-neutral store identity, composite organization foreign keys, and safe backfill of existing Shopify connections.
2. Bind each integration connection to a store; bind channel installations to one or more stores with explicit selection for ambiguous channels.
3. Persist immutable resolved store context on each conversation and execution, derived from verified webhook identity or registered widget installation, never model-supplied IDs.
4. Introduce provider-neutral commerce adapters and normalized product/search/order contracts; Shopify and WooCommerce implementations remain infrastructure.
5. Enforce store, organization, connection, channel, agent capability and publication visibility on every tool.
6. Use sync + webhooks + reconciliation; distinguish empty catalog from failed/stale sync.
7. Implement channel-specific text/card rendering and outbound delivery for widget, WhatsApp, Messenger.
8. Keep OTP verification scoped to store, conversation and order; do not reuse across channels.

## Safety
Never use PDF/RAG excerpts as proof of current inventory. Do not allow implicit cross-store fallback. Fail closed when store identity is ambiguous. Preserve existing integration and conversation records through additive migrations.
