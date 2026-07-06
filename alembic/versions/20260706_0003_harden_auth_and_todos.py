"""harden auth ownership and todo constraints"""

from datetime import datetime

import bcrypt
from alembic import op
import sqlalchemy as sa

import config

revision = "20260706_0003"
down_revision = "20260625_0002"
branch_labels = None
depends_on = None


def _hash_default_password() -> str:
    return bcrypt.hashpw(
        config.DEFAULT_ADMIN_PASSWORD.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def _ensure_default_user(bind) -> int:
    result = bind.execute(
        sa.text("SELECT id FROM users WHERE username = :username"),
        {"username": config.DEFAULT_ADMIN_USERNAME},
    ).fetchone()
    if result:
        return int(result[0])

    inserted = bind.execute(
        sa.text(
            "INSERT INTO users "
            "(username, email, password_hash, display_name, created_at) "
            "VALUES (:username, :email, :password_hash, :display_name, :created_at) "
            "RETURNING id"
        ),
        {
            "username": config.DEFAULT_ADMIN_USERNAME,
            "email": config.DEFAULT_ADMIN_EMAIL,
            "password_hash": _hash_default_password(),
            "display_name": config.DEFAULT_ADMIN_DISPLAY_NAME,
            "created_at": datetime.now(),
        },
    ).fetchone()
    return int(inserted[0])


def upgrade() -> None:
    bind = op.get_bind()
    admin_id = _ensure_default_user(bind)

    bind.execute(
        sa.text("UPDATE meetings SET user_id = :user_id WHERE user_id IS NULL"),
        {"user_id": admin_id},
    )
    bind.execute(
        sa.text(
            "UPDATE todo_items "
            "SET user_id = COALESCE(todo_items.user_id, meetings.user_id, :user_id) "
            "FROM meetings "
            "WHERE todo_items.meeting_id = meetings.id "
            "AND (todo_items.user_id IS NULL OR todo_items.user_id <> meetings.user_id)"
        ),
        {"user_id": admin_id},
    )

    op.create_check_constraint(
        "ck_todo_items_status_valid",
        "todo_items",
        "status IN ('pending', 'done', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_todo_items_priority_valid",
        "todo_items",
        "priority IN ('high', 'medium', 'low')",
    )
    op.create_check_constraint(
        "ck_todo_status_logs_to_status_valid",
        "todo_status_logs",
        "to_status IN ('pending', 'done', 'cancelled')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_todo_status_logs_to_status_valid", "todo_status_logs", type_="check")
    op.drop_constraint("ck_todo_items_priority_valid", "todo_items", type_="check")
    op.drop_constraint("ck_todo_items_status_valid", "todo_items", type_="check")
