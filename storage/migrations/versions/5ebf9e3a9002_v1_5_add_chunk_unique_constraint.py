"""v1.5_add_chunk_unique_constraint

Revision ID: 5ebf9e3a9002
Revises: 662a20a42c74
Create Date: 2026-05-25 22:45:33.837988

清理旧数据（chunk_type='unknown' 的 server_default 残留行），
然后添加 UNIQUE(meeting_id, chunk_type, chunk_index) 约束作为数据库层兜底。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5ebf9e3a9002'
down_revision: Union[str, Sequence[str], None] = '662a20a42c74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 清理 server_default 残留：旧数据无 chunk_type 元信息，无法满足唯一约束
    op.execute("DELETE FROM meeting_chunks WHERE chunk_type = 'unknown'")

    op.create_unique_constraint(
        "uq_meeting_chunks_mid_ctype_cidx",
        "meeting_chunks",
        ["meeting_id", "chunk_type", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_meeting_chunks_mid_ctype_cidx",
        "meeting_chunks",
        type_="unique",
    )
