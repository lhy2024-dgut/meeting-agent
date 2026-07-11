"""add users and meeting ownership"""

from datetime import datetime

import bcrypt
from alembic import op
import sqlalchemy as sa

import config

revision = "20260625_0001"
down_revision = "5ebf9e3a9002"
branch_labels = None
depends_on = None


def _hash_default_password() -> str:
    return bcrypt.hashpw(
        config.DEFAULT_ADMIN_PASSWORD.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.add_column("meetings", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index("ix_meetings_user_id", "meetings", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_meetings_user_id_users",
        "meetings",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT id FROM users WHERE username = :username"),
        {"username": config.DEFAULT_ADMIN_USERNAME},
    ).fetchone()
    if result:
        admin_id = result[0]
    else:
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
        admin_id = inserted[0]

    bind.execute(
        sa.text("UPDATE meetings SET user_id = :user_id WHERE user_id IS NULL"),
        {"user_id": admin_id},
    )

    op.alter_column("meetings", "user_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint("fk_meetings_user_id_users", "meetings", type_="foreignkey")
    op.drop_index("ix_meetings_user_id", table_name="meetings")
    op.drop_column("meetings", "user_id")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
