"""Add isolated MCP OAuth state.

Revision ID: f735e89a10bc
Revises: c94e10635a27
"""

import sqlalchemy as sa
from alembic import op

revision = "f735e89a10bc"
down_revision = "c94e10635a27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_authorizations_v2",
        sa.Column("request_hash", sa.String(64), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("session_hash", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mcp_grants_v2",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_name", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_mcp_grants_v2_user_id", "mcp_grants_v2", ["user_id"])
    op.create_table(
        "mcp_codes_v2",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "grant_id",
            sa.Integer(),
            sa.ForeignKey("mcp_grants_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("code_challenge_method", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "mcp_credentials_v2",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "grant_id",
            sa.Integer(),
            sa.ForeignKey("mcp_grants_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("mcp_credentials_v2")
    op.drop_table("mcp_codes_v2")
    op.drop_index("ix_mcp_grants_v2_user_id", table_name="mcp_grants_v2")
    op.drop_table("mcp_grants_v2")
    op.drop_table("mcp_authorizations_v2")
