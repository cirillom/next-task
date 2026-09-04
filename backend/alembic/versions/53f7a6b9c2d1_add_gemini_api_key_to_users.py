"""add encrypted Gemini API key to users

Revision ID: 53f7a6b9c2d1
Revises: 26e6f49a7567
Create Date: 2026-09-03 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "53f7a6b9c2d1"
down_revision: str | None = "26e6f49a7567"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("gemini_api_key_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("gemini_api_key_encrypted")
