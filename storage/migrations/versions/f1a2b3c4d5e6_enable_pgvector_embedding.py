"""enable_pgvector_embedding

Revision ID: f1a2b3c4d5e6
Revises: 5ebf9e3a9002
Create Date: 2026-06-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '5ebf9e3a9002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("ALTER TABLE meeting_chunks ALTER COLUMN embedding TYPE vector(1024) USING NULL")

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding
        ON meeting_chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
    op.execute("ALTER TABLE meeting_chunks ALTER COLUMN embedding TYPE text USING NULL")
