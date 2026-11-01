"""Persist compact, conversation-scoped product shopping preferences."""

import sqlalchemy as sa
from alembic import op

revision = "0027_conversation_shopping_state"
down_revision = "0026_ai_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("shopping_state", sa.JSON(), nullable=True))
    op.add_column("conversations", sa.Column("shopping_state_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("shopping_state_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM conversations WHERE shopping_state IS NOT NULL")
    ).scalar_one()
    if count:
        raise RuntimeError("Cannot remove shopping state while active conversation state is stored.")
    op.drop_column("conversations", "shopping_state_expires_at")
    op.drop_column("conversations", "shopping_state_updated_at")
    op.drop_column("conversations", "shopping_state")
