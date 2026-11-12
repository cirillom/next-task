"""Operator-issued invitations; SMTP never holds a database transaction open."""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.auth.security import hash_token
from app.database import SessionLocal
from app.models import Invitation, User
from app.services.mail import normalize_email_address, public_app_url, send_email

INVITATION_LIFETIME = timedelta(hours=24)


def send_invitation(address: str) -> None:
    email = normalize_email_address(address)
    url = public_app_url()
    token = secrets.token_urlsafe(32)
    digest = hash_token(token)
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            raise ValueError("An account with that email already exists. Use password recovery.")
        insert = postgres_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        statement = insert(Invitation).values(
            email=email,
            token_hash=digest,
            expires_at=datetime.now(UTC) + INVITATION_LIFETIME,
        )
        db.execute(
            statement.on_conflict_do_update(
                index_elements=[Invitation.email],
                set_={
                    name: getattr(statement.excluded, name) for name in ("token_hash", "expires_at")
                },
            )
        )
        db.commit()
    try:
        send_email(
            email,
            "You're invited to Next Task",
            "Use this link to create your Next Task account. It expires in 24 hours and "
            "works once. If you did not expect this invitation, ignore this email.\n\n"
            f"{url}/#/accept-invite?token={token}\n",
        )
    except Exception:
        # Never resurrect an old link or remove a newer, concurrently issued invitation.
        with SessionLocal() as db:
            db.execute(delete(Invitation).where(Invitation.token_hash == digest))
            db.commit()
        raise
