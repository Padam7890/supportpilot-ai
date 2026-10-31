# Backend setup: Sprint 2 foundation and Sprint 3 workflows

Install dependencies from `backend/`:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```
Set `DATABASE_URL` and `REDIS_URL` for your environment. Generate a JWT secret with
`python -c "import secrets; print(secrets.token_urlsafe(48))"` and set `JWT_SECRET`.
The runtime database role must be non-superuser and `NOBYPASSRLS`. Use the
separate migration role for Alembic.

## Migrations

From the repository root, the local Compose migration job uses the privileged
migration role:

```bash
docker compose run --build --rm migrate
```

The migration validates tenant relationships before creating composite foreign
keys. It stops without rewriting existing rows if it finds cross-organization
references.

For a standalone backend environment, point `DATABASE_URL` at the migration
role only for this command, then restore the restricted runtime URL:

```bash
alembic upgrade head
```

## Run API
```bash
uvicorn app.main:app --reload
```

## RLS notes
The migration enables and forces RLS on users, customers, tickets, conversations and messages.
Every authenticated request sets `app.current_tenant` transaction-locally from a signed JWT claim.
The organization table is intentionally not RLS-protected because login/register must resolve a tenant before tenant context exists; only public organization metadata (name/slug/id) is stored there.
Do not run the application with a PostgreSQL superuser or a role with BYPASSRLS. Create a dedicated least-privilege application role for production.

Sprint 3 adds short-lived access JWTs, rotating refresh sessions, owner/admin
team invitations, role checks, ticket activity, customer and ticket search,
pagination, aggregate statistics, and message sender names. API responses return
`items`, `total`, `limit`, and `offset` for paginated collections.

New tenant registrations remain pending and receive no session until approved by
a platform owner. Existing tenants are migrated as approved. After applying
migrations, create the initial isolated platform owner once with:

```bash
python -m app.cli create-platform-owner
```

Platform owners sign in separately at `/platform/login` and can approve, reject,
or reopen tenant registrations. Tenant Owners/Admins continue to onboard team
members through the existing one-time invite flow.
