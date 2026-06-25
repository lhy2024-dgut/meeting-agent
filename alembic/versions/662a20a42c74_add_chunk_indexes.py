"""add chunk metadata indexes"""

from alembic import op

revision = "662a20a42c74"
down_revision = "86cee12a749a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_meeting_chunks_mid_ctype_cidx",
        "meeting_chunks",
        ["meeting_id", "chunk_type", "chunk_index"],
    )
    op.create_index(
        "ix_meeting_chunks_content_hash",
        "meeting_chunks",
        ["content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_meeting_chunks_content_hash", table_name="meeting_chunks")
    op.drop_index("ix_meeting_chunks_mid_ctype_cidx", table_name="meeting_chunks")
