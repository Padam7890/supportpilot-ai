# SupportPilot AI — Codex Engineering Instructions

## Project Context

SupportPilot AI is a production-oriented, multi-tenant AI customer support and commerce automation SaaS.

The platform supports AI conversations, RAG, human handoff, inbox management, commerce integrations, product recommendations and future integrations such as WhatsApp, Facebook Messenger and WooCommerce.

Primary engineering goals:

- Maintainable and scalable architecture
- Strong tenant isolation and security
- Reliable AI workflows
- Provider-independent integrations
- Clean, readable, testable code
- Backward compatibility
- Minimal unnecessary complexity

## 1. Repository Understanding

Before implementing any task:

1. Inspect the relevant existing code and repository structure.
2. Read existing architecture documentation and applicable nested AGENTS.md files.
3. Identify reusable services, components, utilities and interfaces.
4. Understand current database relationships and API contracts.
5. Follow established conventions unless there is a strong reason to change them.
6. Avoid creating duplicate implementations.

Never assume a module, endpoint, table or dependency exists without verifying it.

## 2. Architecture

- Prefer a modular monolith unless the repository already uses another established architecture.
- Apply SOLID principles pragmatically.
- Separate domain, application, infrastructure and presentation responsibilities where complexity justifies it.
- Use dependency injection where appropriate.
- Keep controllers and route handlers thin.
- Place business logic in focused application or domain services.
- Keep commerce-provider-specific logic inside adapters.
- Keep AI-provider-specific logic behind interfaces.
- Avoid circular dependencies and unnecessary abstractions.
- Do not introduce microservices without explicit approval.

Recommended dependency direction:

Presentation → Application → Domain

Infrastructure implements interfaces required by the application or domain.

## 3. Folder Structure

Follow the existing repository structure first.

For substantial new backend modules, prefer:

src/modules/<feature>/
- application/
- domain/
- infrastructure/
- presentation/
- tests/

Do not force this structure onto simple features that do not require it.

For frontend features, prefer:

features/<feature>/
- components/
- hooks/
- api/
- types/
- utils/
- tests/

Use descriptive filenames and colocate related functionality.

## 4. TypeScript Quality

- Use strict TypeScript.
- Avoid `any`, unsafe casts and non-null assertions.
- Validate untrusted input at runtime.
- Prefer discriminated unions for stateful responses.
- Use explicit contracts at module boundaries.
- Prefer descriptive function and variable names.
- Keep functions focused.
- Use early returns when they improve readability.
- Avoid deeply nested conditionals.
- Avoid magic numbers and unexplained constants.
- Do not suppress compiler or lint errors without justification.

## 5. Database and Multi-Tenancy

- Every tenant-owned operation must enforce organization ownership.
- Never trust organization IDs supplied by unauthenticated clients.
- Derive tenant context from verified authentication and authorization.
- Use safe schema migrations.
- Add indexes and constraints based on actual query patterns.
- Use transactions for logically atomic operations.
- Avoid N+1 queries.
- Use exact monetary representations.
- Handle pagination and large datasets efficiently.
- Do not execute destructive migrations without explicit approval.
- Preserve existing data and backward compatibility.

## 6. AI and LLM Engineering

Treat LLM output and retrieved content as untrusted.

- Validate model-generated structured output.
- Validate AI tool inputs and outputs.
- Never fabricate products, prices, stock, specifications or customer records.
- Never execute arbitrary model-generated SQL or code.
- Keep deterministic business rules outside the LLM.
- Apply authorization checks inside backend tools.
- Use bounded retries and timeouts.
- Handle model failures and malformed responses.
- Track token usage, latency and estimated costs.
- Avoid unnecessary LLM calls.
- Do not expose system prompts, API keys or private tenant data.
- Prevent prompt injection from retrieved documents and catalog content.

## 7. Integrations

Design integrations to support future providers without rewriting core business logic.

- Use provider adapters and explicit capability contracts.
- Keep provider SDKs inside integration infrastructure.
- Verify webhook signatures.
- Handle rate limits and transient failures.
- Use idempotency for retried operations.
- Support incremental synchronization where appropriate.
- Never hardcode provider credentials.
- Avoid provider-specific assumptions in shared domain code.
- Implement graceful degradation when external services fail.

## 8. Product Recommendations

For recommendation features:

- Retrieve products only from the authorized merchant catalog.
- Enforce strict customer constraints before ranking.
- Separate hard constraints from soft preferences.
- Validate prices, variants and availability.
- Rank products using testable business logic.
- Ground AI explanations in verified product attributes.
- Handle missing data without hallucination.
- Support conversational preference refinement.
- Return structured, typed recommendation responses.
- Keep recommendation logic independent of chat channels.
- Revalidate consequential commerce actions against the authoritative provider.

## 9. Frontend

- Reuse the existing design system and component library.
- Prefer small, reusable, accessible components.
- Keep business logic outside presentation components.
- Use typed API contracts.
- Provide loading, empty, error and success states.
- Support mobile and desktop.
- Avoid unnecessary rerenders and expensive computations.
- Do not render untrusted HTML.
- Maintain existing UI behavior unless the task requires changes.

## 10. Security

- Enforce authentication and authorization server-side.
- Validate input at trust boundaries.
- Protect against cross-tenant data access.
- Never expose secrets in logs or API responses.
- Avoid logging unnecessary sensitive customer data.
- Apply least-privilege access.
- Protect state-changing operations from replay and duplication.
- Do not weaken security controls to make tests pass.

## 11. Testing

For every meaningful behavior change:

- Add or update relevant tests.
- Test business rules independently.
- Test positive, negative and edge cases.
- Test tenant isolation where applicable.
- Test provider failures and malformed external responses.
- Add regression tests for fixed bugs.
- Preserve existing passing tests.
- Never delete or weaken tests simply to achieve a passing build.

Run the relevant available checks before reporting completion.

## 12. Maintainability

- Prefer simple solutions over clever abstractions.
- Avoid premature optimization.
- Avoid duplicated business logic.
- Avoid unnecessary dependencies.
- Keep files cohesive.
- Refactor only when necessary for the task.
- Document important architectural decisions.
- Preserve public interfaces unless changes are explicitly required.
- Avoid unrelated formatting changes or broad rewrites.

## 13. Codex Execution Workflow

For every task:

1. Read relevant code and instructions.
2. Identify the smallest safe implementation scope.
3. Explain the plan for substantial changes.
4. Implement incrementally.
5. Add or update tests.
6. Run relevant validation commands.
7. Review the diff for unintended changes.
8. Summarize the implementation and remaining risks.

For multi-phase tasks, complete only the requested phase.

Do not automatically begin the next phase.

## 14. Final Response Format

After implementation, report:

### Implemented
- What changed and why

### Files Changed
- Important created or modified files

### Validation
- Tests, lint, type checks and build results

### Risks
- Known limitations, missing permissions or blockers

### Next Step
- Recommended next phase

Never claim that a test or command passed unless it actually ran successfully.

## 15. Forbidden Practices

Never:

- Rewrite unrelated working modules.
- Introduce dependencies without justification.
- Bypass tenant authorization.
- Hardcode secrets.
- Invent external API capabilities.
- Generate fake production data.
- Ignore failed tests.
- Hide errors with empty catch blocks.
- Introduce breaking API changes silently.
- Perform destructive database operations without approval.
- Deploy to production without explicit authorization.
