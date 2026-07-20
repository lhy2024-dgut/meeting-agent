"""add token revocation state and rotate the historical default admin password"""

import secrets

import bcrypt
from alembic import op
import sqlalchemy as sa


revision = "20260711_0006"
down_revision = "20260711_0005"
branch_labels = None
depends_on = None

_LEGACY_DEFAULT_PASSWORD = b"ChangeMe123!"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, password_hash FROM users"))
    for user_id, password_hash in rows:
        if password_hash and bcrypt.checkpw(
            _LEGACY_DEFAULT_PASSWORD,
            password_hash.encode("utf-8"),
        ):
            replacement = secrets.token_urlsafe(24).encode("utf-8")
            bind.execute(
                sa.text("UPDATE users SET password_hash = :password_hash WHERE id = :user_id"),
                {
                    "user_id": user_id,
                    "password_hash": bcrypt.hashpw(replacement, bcrypt.gensalt()).decode("utf-8"),
                },
            )


def downgrade() -> None:
    op.drop_column("users", "token_version")
