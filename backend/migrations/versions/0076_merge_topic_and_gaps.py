"""Join the conversation topic and knowledge gap migration branches."""

revision = "0076_merge_topic_and_gaps"
down_revision = ("0074_conversation_topic_state", "0075_knowledge_gap_groups")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
