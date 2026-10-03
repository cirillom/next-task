"""Store the combined Next filter on Pomodoro sessions.

Revision ID: f6c7a0d92e31
Revises: e42a91c70d12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6c7a0d92e31"
down_revision: str | None = "e42a91c70d12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pomodoro_sessions", sa.Column("scope_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pomodoro_sessions", "scope_json")
