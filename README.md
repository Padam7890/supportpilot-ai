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
git clone https://github.com/Padam786/supportpilot-ai
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
```

## Services

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| Readiness | http://localhost:8000/health/ready |

## Development

Backend tests:

```bash
docker compose exec api pytest -q
```

Backend lint:

```bash
docker compose exec api ruff check app tests
```

Frontend lint:

```bash
docker compose exec frontend npm run lint
```

## Project Status

Sprint 1: Infrastructure and foundation.

## License

MIT
