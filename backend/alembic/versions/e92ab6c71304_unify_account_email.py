"""Remove separate contact emails after unifying account email verification.

Revision ID: e92ab6c71304
Revises: d8f7a20c6b41
"""

import sqlalchemy as sa
from alembic import op

revision = "e92ab6c71304"
down_revision = "d8f7a20c6b41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A previously verified contact address does not verify a different login.
    op.execute("""
        UPDATE users SET contact_email_verified_at = NULL
        WHERE contact_email IS NULL OR contact_email != email
    """)
    op.drop_index("ix_users_contact_email", table_name="users")
    op.drop_column("users", "contact_email")
    op.alter_column("users", "contact_email_verified_at", new_column_name="email_verified_at")
    op.drop_column("email_verifications", "requested_at")


def downgrade() -> None:
    op.alter_column("users", "email_verified_at", new_column_name="contact_email_verified_at")
    op.add_column("users", sa.Column("contact_email", sa.String(320)))
    op.execute("""
        UPDATE users SET contact_email = email WHERE contact_email_verified_at IS NOT NULL
    """)
    op.create_index("ix_users_contact_email", "users", ["contact_email"], unique=True)
    op.add_column("email_verifications", sa.Column("requested_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE email_verifications SET requested_at = datetime(expires_at, '-24 hours')")
    with op.batch_alter_table("email_verifications") as batch:
        batch.alter_column("requested_at", nullable=False)
