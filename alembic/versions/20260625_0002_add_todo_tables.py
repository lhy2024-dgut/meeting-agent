"""add todo tables"""

from alembic import op
import sqlalchemy as sa

revision = "20260625_0002"
down_revision = "20260625_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "todo_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("assignee", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_todo_items_user_id", "todo_items", ["user_id"], unique=False)
    op.create_index("ix_todo_items_meeting_id", "todo_items", ["meeting_id"], unique=False)

    op.create_table(
        "todo_status_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("todo_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("changed_by", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("changed_at", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["todo_id"], ["todo_items.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_todo_status_logs_todo_id", "todo_status_logs", ["todo_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_todo_status_logs_todo_id", table_name="todo_status_logs")
    op.drop_table("todo_status_logs")
    op.drop_index("ix_todo_items_meeting_id", table_name="todo_items")
    op.drop_index("ix_todo_items_user_id", table_name="todo_items")
    op.drop_table("todo_items")
