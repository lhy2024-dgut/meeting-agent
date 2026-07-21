"""add speaker column to transcriptions"""

from alembic import op
import sqlalchemy as sa


revision = "20260720_0008"
down_revision = "20260714_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transcriptions",
        sa.Column("speaker", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transcriptions", "speaker")
