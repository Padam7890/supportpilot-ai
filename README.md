# SupportPilot AI

AI-powered customer support and operations platform.

## Tech Stack

- Next.js
- TypeScript
- Python
- FastAPI
- PostgreSQL
- pgvector
- Redis
- LangGraph (planned)

## Architecture

SupportPilot AI is designed as a multi-tenant SaaS
application with an AI orchestration layer.

## Getting Started

### Requirements

- Docker Desktop
- Git

### Installation

Clone the repository:

```bash
git clone https://github.com/Padam7890/supportpilot-ai
cd supportpilot-ai
```

Configure environment variables:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

Update the database password in `.env`, and use the same password in `backend/.env`'s `DATABASE_URL`.

Start the application:

```bash
docker compose up --build -d
docker compose run --rm migrate
```

The first database initialization creates a restricted runtime role and a
separate migration role. If your existing `postgres_data` volume predates that
setup, run `docker compose exec postgres /docker-entrypoint-initdb.d/002-app-roles.sh`
once before applying migrations.

## Services

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| Readiness | http://localhost:8000/health/ready |

## Development

Backend unit and isolated PostgreSQL integration tests:

```bash
docker compose --profile test run --rm backend-tests
```

Backend lint:

```bash
docker compose exec api ruff check app tests migrations
```

Frontend checks:

```bash
cd frontend
npm run typecheck
npm run lint
npm test
```

After starting the local services and applying migrations, run browser workflows
with `cd frontend && npx playwright install chromium && npm run test:e2e`.

## Project Status

Sprint 3: Tenant-aware authentication, member invitations, customer and ticket
management, dashboard statistics, conversations, activity history, and
PostgreSQL row-level security. The UI uses a Next.js BFF with HttpOnly cookies;
browser code never receives the access or refresh tokens.

The frontend keeps App Router files thin: route groups and pages live in
`frontend/src/app`, business UI, validation, types, and API functions are grouped
under `frontend/src/features`, shared UI lives in `frontend/src/components`,
and transport utilities live in `frontend/src/lib`. Feature modules are added
as their workflows are implemented.

See [backend/README-SPRINT2.md](backend/README-SPRINT2.md) for migration and
database-role setup details.

## License

MIT
