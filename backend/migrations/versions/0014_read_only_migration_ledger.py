"""Limit the application role to reading Alembic's migration version."""

import os
import re

from alembic import op


def _app_role() -> str:
    role = os.environ.get("APP_DB_USER", "supportpilot_app")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", role):
        raise ValueError("APP_DB_USER must be a simple PostgreSQL role identifier")
    return f'"{role}"'

revision = "0014_read_only_migration_ledger"
down_revision = "0013_shopify_auth_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    role = _app_role()
    op.execute(f"REVOKE ALL PRIVILEGES ON TABLE alembic_version FROM {role}")
    op.execute(f"GRANT SELECT ON TABLE alembic_version TO {role}")


def downgrade() -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE alembic_version TO {_app_role()}")
