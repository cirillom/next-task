"""add MCP OAuth tables

Revision ID: 8d2f4b7c1a90
Revises: 53f7a6b9c2d1
Create Date: 2026-09-03 23:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8d2f4b7c1a90"
down_revision: str | None = "53f7a6b9c2d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_clients",
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("client_id"),
    )
    op.create_table(
        "mcp_authorization_codes",
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scopes_json", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_uri_provided_explicitly", sa.Boolean(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["client_id"], ["mcp_oauth_clients.client_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("code_hash"),
    )
    with op.batch_alter_table("mcp_authorization_codes") as batch_op:
        batch_op.create_index(batch_op.f("ix_mcp_authorization_codes_client_id"), ["client_id"])
        batch_op.create_index(batch_op.f("ix_mcp_authorization_codes_user_id"), ["user_id"])
        batch_op.create_index(batch_op.f("ix_mcp_authorization_codes_expires_at"), ["expires_at"])

    op.create_table(
        "mcp_oauth_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("access_token_hash", sa.String(length=64), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scopes_json", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["client_id"], ["mcp_oauth_clients.client_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("access_token_hash"),
        sa.UniqueConstraint("refresh_token_hash"),
    )
    with op.batch_alter_table("mcp_oauth_tokens") as batch_op:
        batch_op.create_index(batch_op.f("ix_mcp_oauth_tokens_client_id"), ["client_id"])
        batch_op.create_index(batch_op.f("ix_mcp_oauth_tokens_user_id"), ["user_id"])
        batch_op.create_index(
            batch_op.f("ix_mcp_oauth_tokens_access_expires_at"), ["access_expires_at"]
        )
        batch_op.create_index(
            batch_op.f("ix_mcp_oauth_tokens_refresh_expires_at"), ["refresh_expires_at"]
        )
        batch_op.create_index(batch_op.f("ix_mcp_oauth_tokens_revoked_at"), ["revoked_at"])


def downgrade() -> None:
    with op.batch_alter_table("mcp_oauth_tokens") as batch_op:
        batch_op.drop_index(batch_op.f("ix_mcp_oauth_tokens_revoked_at"))
        batch_op.drop_index(batch_op.f("ix_mcp_oauth_tokens_refresh_expires_at"))
        batch_op.drop_index(batch_op.f("ix_mcp_oauth_tokens_access_expires_at"))
        batch_op.drop_index(batch_op.f("ix_mcp_oauth_tokens_user_id"))
        batch_op.drop_index(batch_op.f("ix_mcp_oauth_tokens_client_id"))
    op.drop_table("mcp_oauth_tokens")
    with op.batch_alter_table("mcp_authorization_codes") as batch_op:
        batch_op.drop_index(batch_op.f("ix_mcp_authorization_codes_expires_at"))
        batch_op.drop_index(batch_op.f("ix_mcp_authorization_codes_user_id"))
        batch_op.drop_index(batch_op.f("ix_mcp_authorization_codes_client_id"))
    op.drop_table("mcp_authorization_codes")
    op.drop_table("mcp_oauth_clients")
