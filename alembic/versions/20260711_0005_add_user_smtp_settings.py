"""add per-user smtp settings"""

from alembic import op
import sqlalchemy as sa


revision = "20260711_0005"
down_revision = "20260709_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("smtp_host", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("smtp_port", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("smtp_password", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "smtp_password")
    op.drop_column("users", "smtp_port")
    op.drop_column("users", "smtp_host")
