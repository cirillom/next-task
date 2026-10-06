"""add selected Gemini model to users

Revision ID: a8d42f16b7c3
Revises: c4a1f593d078
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8d42f16b7c3"
down_revision: str | None = "c4a1f593d078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("gemini_model", sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("gemini_model")
