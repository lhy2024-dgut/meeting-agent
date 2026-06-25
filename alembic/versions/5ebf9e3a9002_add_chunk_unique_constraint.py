"""add meeting chunk uniqueness guard"""

from alembic import op

revision = "5ebf9e3a9002"
down_revision = "662a20a42c74"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
