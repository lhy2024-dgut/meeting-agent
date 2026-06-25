"""add chunk metadata to meeting_chunks"""

from alembic import op
import sqlalchemy as sa

revision = "86cee12a749a"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meeting_chunks",
        sa.Column("chunk_type", sa.String(length=32), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "meeting_chunks",
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "meeting_chunks",
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column("meeting_chunks", sa.Column("created_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("meeting_chunks", "created_at")
    op.drop_column("meeting_chunks", "content_hash")
    op.drop_column("meeting_chunks", "chunk_index")
    op.drop_column("meeting_chunks", "chunk_type")
