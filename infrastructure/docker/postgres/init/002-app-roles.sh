#!/bin/sh
set -eu

: "${APP_DB_USER:?APP_DB_USER is required}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required}"
: "${MIGRATION_DB_USER:?MIGRATION_DB_USER is required}"
: "${MIGRATION_DB_PASSWORD:?MIGRATION_DB_PASSWORD is required}"

psql -v ON_ERROR_STOP=1 \
  -v app_role="$APP_DB_USER" \
  -v app_password="$APP_DB_PASSWORD" \
  -v migration_role="$MIGRATION_DB_USER" \
  -v migration_password="$MIGRATION_DB_PASSWORD" \
  -v database_name="$POSTGRES_DB" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN NOBYPASSRLS PASSWORD %L', :'app_role', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role') \gexec
SELECT format('ALTER ROLE %I LOGIN NOBYPASSRLS PASSWORD %L', :'app_role', :'app_password') \gexec

SELECT format('CREATE ROLE %I LOGIN BYPASSRLS PASSWORD %L', :'migration_role', :'migration_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migration_role') \gexec
SELECT format('ALTER ROLE %I LOGIN BYPASSRLS PASSWORD %L', :'migration_role', :'migration_password') \gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'database_name', :'migration_role') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'app_role') \gexec
GRANT USAGE ON SCHEMA public TO :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_role" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_role" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_role";
SQL
