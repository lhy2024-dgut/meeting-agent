"""initial schema for meetings, transcriptions, and meeting_chunks"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "d69ff883dd59"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("audio_path", sa.String(length=500), nullable=True),
        sa.Column("duration_category", sa.String(length=50), nullable=True),
        sa.Column("environment", sa.String(length=100), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("minutes_text", sa.Text(), nullable=True),
        sa.Column("action_items_text", sa.Text(), nullable=True),
        sa.Column("resolutions_text", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_meetings_file_hash"),
        "meetings",
        ["file_hash"],
        unique=False,
        if_not_exists=True,
    )

    op.create_table(
        "transcriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.Float(), nullable=True),
        sa.Column("start_time", sa.Float(), nullable=True),
        sa.Column("end_time", sa.Float(), nullable=True),
        sa.Column("audio_segment", sa.String(length=500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_transcriptions_meeting_id"),
        "transcriptions",
        ["meeting_id"],
        unique=False,
        if_not_exists=True,
    )

    op.create_table(
        "meeting_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_meeting_chunks_meeting_id"),
        "meeting_chunks",
        ["meeting_id"],
        unique=False,
        if_not_exists=True,
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding
        ON meeting_chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
    op.drop_index(op.f("ix_meeting_chunks_meeting_id"), table_name="meeting_chunks")
    op.drop_table("meeting_chunks")
    op.drop_index(op.f("ix_transcriptions_meeting_id"), table_name="transcriptions")
    op.drop_table("transcriptions")
    op.drop_index(op.f("ix_meetings_file_hash"), table_name="meetings")
    op.drop_table("meetings")
