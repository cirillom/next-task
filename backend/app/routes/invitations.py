from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.rate_limit import ip_key, purge_expired_attempts, reserve_window_attempt
from app.auth.security import hash_password, hash_token
from app.database import get_db
from app.models import Invitation, User
from app.schemas import InvitationAccept, Message

router = APIRouter(prefix="/api/auth", tags=["authentication"])
INVALID_INVITATION = "This invitation is invalid or expired. Ask for a new invitation."


@router.post("/invitations/accept", response_model=Message, status_code=201)
def accept_invitation(
    payload: InvitationAccept, request: Request, db: Session = Depends(get_db)
) -> Message:
    now = datetime.now(UTC)
    purge_expired_attempts(db, now)
    client_ip = request.client.host if request.client else "unknown"
    if (
        reserve_window_attempt(
            db, f"invite:{ip_key(client_ip)}", now, window=timedelta(minutes=15), limit=10
        )
        is None
    ):
        raise HTTPException(
            status_code=429, detail="Too many invitation attempts. Try again later."
        )
    # Delete and user creation share one transaction: concurrent redemption has one winner.
    email = db.scalar(
        delete(Invitation)
        .where(Invitation.token_hash == hash_token(payload.token), Invitation.expires_at > now)
        .returning(Invitation.email)
    )
    if email is None:
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)
    db.add(
        User(
            email=email,
            display_name=payload.display_name,
            password_hash=hash_password(payload.password),
            email_verified_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=INVALID_INVITATION) from error
    return Message(message="Account created. Sign in with your email and password.")
