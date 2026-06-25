"""add summary fields to meetings"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "d69ff883dd59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("short_summary", sa.String(length=500), nullable=True))
    op.add_column("meetings", sa.Column("project_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("meetings", "project_name")
    op.drop_column("meetings", "short_summary")
