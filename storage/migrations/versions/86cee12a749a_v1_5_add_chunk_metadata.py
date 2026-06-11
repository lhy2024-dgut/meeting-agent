"""v1.5_add_chunk_metadata

Revision ID: 86cee12a749a
Revises: a1b2c3d4e5f6
Create Date: 2026-05-25 22:28:24.231263
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '86cee12a749a'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('meeting_chunks', sa.Column('chunk_type', sa.String(32), nullable=False, server_default='unknown'))
    op.add_column('meeting_chunks', sa.Column('chunk_index', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('meeting_chunks', sa.Column('content_hash', sa.String(64), nullable=False, server_default=''))
    op.add_column('meeting_chunks', sa.Column('created_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('meeting_chunks', 'created_at')
    op.drop_column('meeting_chunks', 'content_hash')
    op.drop_column('meeting_chunks', 'chunk_index')
    op.drop_column('meeting_chunks', 'chunk_type')
