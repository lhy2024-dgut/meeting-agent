"""preserve manually maintained todos during meeting regeneration"""

from alembic import op
import sqlalchemy as sa


revision = "20260714_0007"
down_revision = "20260711_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "todo_items",
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="meeting_pipeline",
        ),
    )
    op.add_column(
        "todo_items",
        sa.Column(
            "is_user_modified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_check_constraint(
        "ck_todo_items_source_valid",
        "todo_items",
        "source IN ('manual', 'meeting_pipeline')",
    )
    op.alter_column("todo_items", "source", server_default=None)
    op.alter_column("todo_items", "is_user_modified", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_todo_items_source_valid", "todo_items", type_="check")
    op.drop_column("todo_items", "is_user_modified")
    op.drop_column("todo_items", "source")
