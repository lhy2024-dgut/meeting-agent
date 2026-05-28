"""v1.5_add_chunk_unique_index

Revision ID: 662a20a42c74
Revises: 86cee12a749a
Create Date: 2026-05-25 22:37:43.699633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '662a20a42c74'
down_revision: Union[str, Sequence[str], None] = '86cee12a749a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 复合索引：加速 meeting_id + chunk_type 查询，覆盖常见检索路径
    op.create_index(
        "ix_meeting_chunks_mid_ctype_cidx",
        "meeting_chunks",
        ["meeting_id", "chunk_type", "chunk_index"],
    )
    # 独立索引：content_hash 用于去重校验
    op.create_index(
        "ix_meeting_chunks_content_hash",
        "meeting_chunks",
        ["content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_meeting_chunks_content_hash", table_name="meeting_chunks")
    op.drop_index("ix_meeting_chunks_mid_ctype_cidx", table_name="meeting_chunks")
