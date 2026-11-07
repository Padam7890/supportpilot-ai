# SupportPilot AI v1.0 — Multi-Knowledge Base and AI Bots

**Plan version:** 1.0  
**Last reviewed:** 2026-11-06  
**Status:** Local implementation, migration upgrade/backfill/rollback behavior, restricted-role retrieval, API-to-worker citation flow, and service-backed browser flows have been exercised on disposable PostgreSQL. Owner/Admin/Agent/Viewer API authorization and Viewer UI behavior have focused regression coverage. Release acceptance remains open for the broader application accessibility matrix and deployed/staged database state.

## Goal and definition of done

Extend the current SupportPilot workspace so an Owner/Admin can create multiple knowledge bases and AI bots, assign any combination of bases to each bot, and select the appropriate bot for a supported channel. A bot must answer and cite only documents in its assigned, active knowledge bases. The same base can be assigned to multiple bots. Existing workspace knowledge remains available through a default base and bot.

The feature is ready for v1.0 only when the database migration and tenant isolation are verified against PostgreSQL, the dashboard workflow is usable end to end, and the create-base → upload-document → assign-to-bot → cited-answer flow passes its automated browser test.

## Target architecture

Keep this as an extension of the existing FastAPI, SQLAlchemy, PostgreSQL, LangGraph, durable worker, and Next.js modular monolith. Reuse the shared retrieval engine and current provider configuration; do not create a separate RAG service or vector database in this release.

```text
Organization
├── Knowledge Library
│   ├── Products Knowledge
│   ├── Returns & Refunds
│   ├── Shipping & Delivery
│   └── Technical Documentation
├── AI Bots
│   ├── Sales Bot ─────── Products Knowledge + Shipping & Delivery
│   ├── Support Bot ───── Returns & Refunds + Shipping & Delivery
│   └── Technical Bot ─── Technical Documentation
└── Supported channels
    └── Storefront widget / configured inbound connection → selected bot
```

The central relationship is `ai_agents ↔ ai_agent_knowledge_bases ↔ knowledge_bases`. Documents belong to one base. Executions and conversations retain their bot reference. Retrieval checks the authenticated tenant, active bot, current active assignments, and ready/non-deleted document state before assembling both context and citations.

```text
Next.js dashboard / storefront widget
                 │
                 ▼
       FastAPI routes and auth
                 │
                 ▼
      AI application / LangGraph ───── PostgreSQL full-text retrieval
                 │                               │
                 └──────── durable worker ───────┘
```

## Current repository status

| Phase | Repository evidence | Release status |
|---|---|---|
| 1. Database foundation | Migration `0036_knowledge_bases_and_ai_agents` adds tenant-owned bases, bots, assignments, default backfill, and references from documents, widgets, conversations, and executions. A fail-closed downgrade guard now rejects customized workspace configuration. | A fresh disposable PostgreSQL database migrated through `0041`; runtime preflight confirmed forced RLS on 42 tenant tables and a read-only Alembic ledger. Earlier synthetic legacy migration checks backfilled defaults and preserved document/ingestion history through downgrade and re-upgrade. Production DB state remains unverified. |
| 2. Knowledge management APIs | Base CRUD/archive routes and base-aware document upload/list/search use existing versioned APIs. Upload without a base resolves the workspace default. | Full backend PostgreSQL suite passed locally, including cross-tenant assignment rejection and role matrix: Owner/Admin writes allowed, Agent/Viewer writes denied. |
| 3. AI bot management | Bot CRUD, active state, instructions, and base assignment routes exist. Workspace provider configuration remains shared. | Full backend PostgreSQL suite passed locally; Owner/Admin management and Agent/Viewer write denial have API coverage, plus Viewer read-only UI coverage. |
| 4. Agent-scoped RAG | AI context assembly filters documents by the active bot’s current active base assignments and uses those results for citations. | Focused knowledge, AI, and widget integration tests passed on disposable PostgreSQL with the restricted runtime role (`28 passed`, no skips), covering tenant isolation, assignment changes, queued work, scoped citations, and fallback behavior. Staged release remains open. |
| 5. Dashboard UI | Knowledge Library base management, AI Bots page, AI playground selector, and widget bot selector are present. Mocked Playwright coverage includes the cited-answer flow; service-backed Playwright creates a base, uploads/processes a document with the real worker, creates a bot, and verifies assignment persistence. | Partial; local service flow, responsive Viewer read-only Playwright/axe check, and contrast correction passed. Broader application accessibility/release verification remains open. |
| 6. Inbox and channel routing | Widget-selected bot is stored on widget conversations. Inbound-capable provider connections can now select an active tenant bot for new conversations, with default fallback. | Partial; no inbound-messaging provider is currently registered, and the routing migration/API/UI remain unverified. |
| 7. Production hardening | Full backend suite, migrations, runtime-role/RLS preflight, frontend checks, and focused browser checks ran locally on disposable resources. | Release gate remains open for deployed/staged DB state, full role/accessibility matrix, and rollout monitoring. |

Latest local verification snapshot (2026-11-06): backend pytest passed (`351 passed`, no skips) against disposable PostgreSQL using the restricted `supportpilot_app` role; migration upgrade reached `0041_automation_canvas_layout`, runtime preflight verified forced RLS on 42 tenant tables and read-only Alembic ledger access, and the focused Knowledge/AI/Widget suite passed (`28 passed`). The added composite-FK regression rejects cross-tenant bot/base assignment. Backend Ruff and OpenAPI export drift passed. Frontend ESLint, TypeScript, Vitest (`78 passed`), generated API type drift, and production build passed. A serial local Playwright acceptance set passed (`12 passed`), including the Knowledge/Bot setup and role views plus the shell accessibility check. Full registration/approval/OTP/password-recovery E2E requires API, database, platform-owner, and Mailpit services and was not run. Earlier synthetic legacy migration checks verified default backfill, document/source/chunk/ingestion-history preservation, guarded downgrade, and re-upgrade. Deployed database state and staged rollout remain unverified.


Earlier sandbox audit snapshot (2026-11-06): backend pytest passed `329` tests, and frontend Vitest passed `53` tests; the newer local verification immediately above supersedes these counts. Dashboard shell Playwright (`6 passed`) and mocked Knowledge/Bot Playwright (`4 passed`) are prior browser results, not fresh results from the current continuation. These checks use disposable local resources; deployed/staged rollout remains unverified.

## Phase-by-phase release plan

### Phase 1 — Database foundation — implemented locally; live verification open

- Keep migration 0036 additive and ordered after `0035_shared_auth_identities`.
- Create a default active knowledge base and bot per existing organization; assign existing documents, widgets, conversations, and executions without deleting or rewriting document/ingestion history.
- Create the default base and bot for each newly registered organization within the registration transaction and tenant context.
- Verify forced RLS on all new tables, same-tenant composite foreign keys, indexes, default uniqueness, backfill counts, and safe upgrade/downgrade behavior on PostgreSQL.

### Phase 2 — Knowledge management APIs — implemented locally; acceptance open

- Preserve `/api/v1/knowledge/bases` list/create/get/update/archive APIs and existing document routes.
- Support optional `knowledge_base_id` on document upload, listing, and search; resolve omitted upload base to the default and reject archived or cross-tenant bases.
- Require Owner/Admin for base and document configuration changes; keep tenant filtering and database constraints as independent protections.
- Verify pagination, upload and search behavior, archive rules, permissions, tenant isolation, and existing ingestion status/history.

### Phase 3 — AI bot management — implemented locally; acceptance open

- Preserve `/api/v1/ai/agents` list/create/get/update, knowledge-base assignment, and activate/deactivate operations.
- Keep provider/model credentials in server-side workspace configuration. Bot-level configuration in v1.0 is limited to name, instructions, assigned bases, and activation state.
- Require Owner/Admin to change bot configuration; preserve a non-deactivatable default bot for compatibility.
- Verify an active base can be shared between bots, assignment changes are atomic, and inactive or cross-tenant bases cannot be assigned.

### Phase 4 — Agent-scoped RAG — implemented locally; acceptance open

- Resolve the bot from authenticated execution input, its conversation, or trusted server-side widget configuration. Never accept bot or organization selection from an unauthenticated visitor.
- At retrieval time, use the bot’s current assignments, so removal of a base also affects work that is queued but has not retrieved context yet.
- Limit both retrieved context and citations to the same tenant-scoped query over active assigned bases and ready, non-deleted documents.
- Return the existing safe no-knowledge behavior for inactive bots, empty assignments, and no matching documents. Do not grant implicit access to all tenant bases.
- Keep the existing PostgreSQL full-text search; vector search is deferred.

### Phase 5 — Dashboard UI — partial; verify before release

- Complete the Knowledge Library flow for creating/selecting/archiving bases and uploading, searching, and managing documents within the selected base.
- Complete the AI Bots flow for creating/editing instructions, assigning multiple bases, and activating/deactivating bots.
- Keep bot selection in the AI playground and widget settings; default to the workspace bot when no explicit selection is configured.
- Verify Owner/Admin write controls, read-only roles, responsive layout, keyboard/accessibility behavior, and loading/empty/error/success states. A service-backed local browser test now covers base creation, document ingestion, bot assignment, and persistence through the live API/worker; role and full accessibility coverage remain open.

### Phase 6 — Inbox and channel routing — partial; only implemented channels

- Retain bot identity on conversations and AI executions for audit and consistent routing.
- Keep storefront widget routing bound to the bot selected in trusted widget configuration.
- Where an existing inbound connection supports configuration, allow it to select an active tenant bot; preserve the default bot as the compatibility fallback when no selection exists.
- Verify human takeover, AI mode, and existing safe reply controls continue to work with bot-specific context.
- Do not add WhatsApp, Messenger, or other provider implementations in v1.0.

**Per-connection bot routing (implemented locally, validation deferred, 2026-11-07):** Added an optional tenant-scoped AI bot selection to integration connections that declare inbound messaging. New inbound conversations use that active bot; an unset or deactivated selection falls back to the tenant default. Existing conversations retain their stored bot. Owners/Admins can configure routing in Integrations when a real inbound-capable provider is registered; unsupported or disconnected connections are rejected, and routing changes are recorded in the existing secret-free connection audit. The additive migration is `0059_integration_ai_bot_routing`, after `0058_first_response_sla_policy`; neither migration has been applied. The current registry has no inbound-messaging adapter, so no selector appears for the currently registered Shopify capabilities. OpenAPI and generated TypeScript contracts were refreshed. No tests or runtime checks were run per the feature-only instruction.

### Phase 7 — Production hardening — release gate

- Run upgrade and rollback validation on an isolated PostgreSQL database using the migrator role; run application tests using the restricted runtime role. Local migration/RLS and service-backed flow checks have run on disposable infrastructure.
- Verify RLS, tenant-aware foreign-key rejection, role boundaries, default backfill, assignment sharing/removal, citations, and cross-tenant retrieval isolation.
- Add or complete tests for widget/playground/reply-draft routing, inactive and unassigned bots, archive/deletion behavior, and queued execution after assignment changes.
- Run OpenAPI export and generated TypeScript drift checks, backend Ruff and pytest, frontend lint/typecheck/Vitest/build, and Playwright for the full cited-answer flow.
- Stage the migration and feature for one internal workspace first. Monitor migration/readiness status, worker failures, AI execution failures, and retrieval/citation correctness before expanding.
- Prefer application rollback that leaves migration 0036 and its data in place. If a schema downgrade is needed, stop workers/readers first and review the downgrade’s effect on custom bot/base configuration; preserve document rows and ingestion history, and never use a downgrade to clear tenant content.

## Public interfaces and compatibility

- Keep existing versioned route names and response shapes: `/api/v1/knowledge/bases`, `/api/v1/ai/agents`, and current document APIs.
- Keep `knowledge_base_id` optional for existing document operations and `ai_agent_id` optional for authenticated AI requests. Resolve missing values on the server using the workspace default or conversation/widget binding.
- Keep widget bot selection in authenticated tenant configuration. Public widget requests may identify the widget but cannot choose a bot or tenant.
- Store the selected bot and configuration version on executions. Store the bot on conversations so replies and later executions use the intended channel binding.
- No per-bot model/provider credentials are introduced. Existing workspace AI provider settings remain authoritative.

## Test and release acceptance

The v1.0 acceptance suite must prove all of the following:

1. Existing organizations receive one default base and bot; existing documents and relevant records are associated without losing history.
2. An Owner/Admin can create two bases and two bots, assign one base to both bots, and assign a different base to only one bot.
3. Each bot returns grounded answers and citations only from its assigned bases; another tenant’s, archived, deleted, unready, and unassigned documents never appear.
4. Assignment changes affect queued work at retrieval time; inactive/unassigned bot behavior is safe and does not search the whole organization.
5. Widget, AI playground, conversation, and supported inbound connection routing use the selected or default bot as designed.
6. All required database, backend, frontend, contract, and Playwright checks run and pass. Skipped PostgreSQL or browser tests count as unverified, not passed.

## Assumptions and scope

- “v1.0” means this multi-knowledge-base and AI-bot capability release, not a full SupportPilot product-wide version milestone.
- The current local implementation is the baseline; this plan completes and verifies it rather than replacing it.
- The AI provider remains workspace-wide; bot settings do not store credentials.
- The shared PostgreSQL full-text retrieval system remains in use; pgvector and semantic retrieval are deferred.
- Only the storefront widget and currently implemented inbound integration path are in scope. New messaging providers and unrelated recommendation features are out of scope.
