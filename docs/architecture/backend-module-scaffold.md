# Backend architecture scaffold: migration destinations

**Status:** Structure only. No business code, APIs, models, workers, schema or runtime imports moved by this PR.

## Why scaffold first

SupportPilot AI currently mixes `app/features` with legacy `app/api/routes`, `app/services`, `app/repositories`, `app/schemas` and `app/models`. All are active in different ways. Some legacy modules are compatibility exports; others contain authoritative logic. The goal is **one canonical owner per behavior** without a second copy of that implementation.

This PR tracks the destinations for the **currently needed complex features**, using Python `__init__.py` files as safe directory markers. It intentionally does not create empty `service.py`, `repository.py`, `router.py` or `ports.py` files. Create such files only when the first real implementation moves into them.

## Target package layout

```text
backend/app/
├── main.py                    # Existing ASGI entrypoint stays unchanged
├── api/                       # Existing routers/deps retained during migration
├── bootstrap/                 # Future wiring/composition root
├── core/                      # Existing config, security, observability
├── db/                        # Existing SQLAlchemy session / Base; unchanged
├── shared/
│   ├── kernel/                # Only truly universal shared data types
│   ├── application/ports/     # Only shared ports with real multiple consumers
│   └── infrastructure/        # Shared technical adapters, not business logic
├── features/
│   ├── auth/{domain,application,infrastructure,presentation}/
│   ├── customers/{domain,application,infrastructure,presentation}/
│   ├── tickets/{domain,application,infrastructure,presentation}/
│   ├── conversations/{domain,application,infrastructure,presentation}/
│   ├── inbox/{domain,application,infrastructure,presentation}/
│   ├── widgets/{domain,application,infrastructure,presentation}/
│   ├── automations/{domain,application,infrastructure,presentation}/
│   ├── ai/                     # Existing domain/application/infrastructure retained;
│   │   └── presentation/       # New migration destination only
│   ├── knowledge/{domain,application,infrastructure,presentation}/
│   ├── commerce/{domain,application,infrastructure,presentation}/
│   ├── channels/{domain,application,infrastructure,presentation}/
│   ├── notifications/          # Already partly layered; do not duplicate
│   ├── platform/               # Existing platform route destination
│   ├── search/                 # Existing search route destination
│   ├── organizations/          # Remains flat until real decomposition
│   ├── users/                  # Remains flat until real decomposition
│   ├── teams/                  # Remains flat until real decomposition
│   ├── analytics/              # Remains flat until real decomposition
│   ├── attachments/            # Remains flat until real decomposition
│   └── saved_replies/          # Remains flat until real decomposition
├── integrations/               # Existing provider capability registry and adapters
├── workers/                    # Existing durable scheduler / handlers
├── models/                     # Keep centralized for Alembic import compatibility
├── schemas/                    # Legacy API DTOs retained until consumers migrate
├── repositories/               # Compatibility imports retained until consumers migrate
└── services/                   # Legacy implementations/facades; no premature deletion
```

## Ownership and source-file migration map

| Destination module | Source files / current owners to review in a later PR | Notes |
| --- | --- | --- |
| `features/auth` | `features/auth/router.py`, `api/deps.py`, token/session code | Do not change token, CSRF, RLS or rate-limit semantics in a structure PR. |
| `features/customers` | `features/customers/{router,service,repository}.py`; `schemas/customer.py` | Keep response shapes and cross-feature references stable. |
| `features/tickets` | `features/tickets/{router,service,repository,link_service}.py` | Application exceptions must eventually be mapped to HTTP at the boundary. |
| `features/conversations` | `features/conversations/{router,service,repository}.py` | Move provider delivery behind published contracts; keep transactional outbox. |
| `features/inbox` | `features/inbox/{router,repository,sla_policy}.py` | Inbox is largely a read model. Do not invent a separate ticket aggregate. |
| `features/widgets` | `features/widgets/{public_chat,reply_stream,management,order_actions}.py` | Preserve widget origin checks, idempotency, streaming contract and AI enqueue. |
| `features/ai` | `features/ai/*`, `services/{ai_worker,widget_ai}.py`, `api/routes/{ai,ai_agents}.py` | Existing `domain/application/infrastructure` are canonical; add presentation later. Avoid duplicate AI engines. |
| `features/knowledge` | `api/routes/{knowledge,knowledge_bases,knowledge_gaps}.py`; AI knowledge/retrieval modules | Distinguish knowledge ownership from AI query/reasoning orchestration. |
| `features/commerce` | `api/routes/{catalog,commerce_actions,shopify_orders,recommendations,recommendation_settings}.py`, `services/catalog.py` | Provider-independent catalog/order/recommendation use cases; Shopify protocol stays under `integrations/providers/shopify`. |
| `features/channels` | `integrations/messaging/*`, `api/routes/{integrations,integration_management}.py` | Core channel routing/message policies only. Provider connection/token APIs remain in integrations until interface migration. |
| `features/automations` | `features/automations/{router,service,contracts,policy}.py`, worker automation handler | Keep provider actions through capability adapters. |
| `features/platform` | `api/routes/platform.py` | Platform-owner administration is not organization-scoped business data. |
| `features/search` | `api/routes/search.py` | Start with route ownership; split only when needed. |
| `shared/kernel` | New contracts when an actual cross-feature consumer needs them | Do **not** put AI, commerce or tenant persistence implementation in shared. |
| `bootstrap` | Future router/DI composition from `api/router.py`, `main.py`, worker construction | Keep existing startup import graph until a later dedicated PR. |

### Already appropriately organized — do not recreate

- `app/features/ai/domain`, `application`, `infrastructure`
- `app/features/notifications/application`, `infrastructure`, `presentation`
- `app/integrations/core`, `connections`, `credentials`, `providers/shopify`
- `app/workers/application`, `domain`, `handlers`, `infrastructure`
- `app/db/base.py`, `app/db/session.py` and the existing Alembic model registry

## Dependency rules

1. `presentation -> application -> domain`. The domain must not import FastAPI, request schemas, SQLAlchemy models, external integrations or application services.
2. Infrastructure implements application-defined interfaces/ports; only composition roots wire concrete implementations.
3. Cross-feature consumers use a documented `public.py` or stable application contract when that interface is introduced. Do not create blank `public.py` now.
4. Feature-owned SQLAlchemy repository models may remain in `app/models` until a carefully staged Alembic-compatible move. Do not rename tables or import paths merely to achieve visual symmetry.
5. Keep tenant context server-authenticated and enforce `organization_id` scoping, composite foreign keys and PostgreSQL RLS throughout.
6. Transaction boundaries and outbox writes must remain atomic. Avoid external provider calls inside DB transactions where possible.
7. Existing legacy import paths remain until all consumers, tests and monkeypatch sites migrate. Compatibility facades are not duplicate business implementations.
8. All new background jobs must use existing worker lifecycle, retry/lease/fencing, tenant context and idempotency conventions.

## Migration sequence after merging this scaffold

| PR | Next implementation scope | Main acceptance criteria |
| --- | --- | --- |
| 1 | **This scaffold** | Add-only directories and this document. No runtime changes. |
| 2 | **Shared contracts & bootstrap** | Add only needed real context/error/event contracts and router composition. API routes unchanged. |
| 3 | **Customers & tickets** | Migrate real service/repository/HTTP code and temporary compatibility exports. |
| 4 | **Conversations, inbox & widgets** | Preserve ticket/message links, widget origin policy and outbox write semantics. |
| 5 | **Knowledge & retrieval** | One canonical evidence contract; tenant- and AI-agent-scoped retrieval, citations intact. |
| 6 | **AI execution** | One lifecycle from all entrypoints; preserve guard/verification semantics and job leases. |
| 7 | **Commerce & Shopify** | Provider-neutral commerce boundaries and exactly one active Shopify adapter path. |
| 8 | **Channels, automations & notifications** | Stable event/outbox contracts and provider-agnostic dispatch. |
| 9 | **Legacy cleanup** | Remove only demonstrably dead imports; enforce dependency tests and document exclusions. |

For each code migration: use `git mv` to preserve history, update imports, temporarily re-export at the old path, run import/architecture/API/worker tests, compare OpenAPI and Alembic metadata, and keep PRs small.

## Scaffold review checklist

- [ ] No existing source files changed or removed
- [ ] No new routes or implicit `__init__` imports
- [ ] No ORM tables or Alembic revisions changed
- [ ] No worker scheduling, Shopify or AI behavior changed
- [ ] No blank services, repositories or controllers created
- [ ] All new packages include import-safe `__init__.py`
- [ ] Subsequent PRs must supply actual implementations and contract tests
