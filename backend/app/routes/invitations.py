from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.rate_limit import ip_key, purge_expired_attempts, reserve_window_attempt
from app.auth.security import hash_password, hash_token
from app.database import get_db
from app.i18n import localized
from app.models import Invitation, User
from app.schemas import InvitationAccept, Message
from app.services.onboarding import add_onboarding_data

router = APIRouter(prefix="/api/auth", tags=["authentication"])
INVALID_INVITATION = localized("api.thisInvitationIsInvalidOrExpiredAskForA")


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
            status_code=429, detail=localized("api.tooManyInvitationAttemptsTryAgainLater")
        )
    # Delete and user creation share one transaction: concurrent redemption has one winner.
    invitation = db.execute(
        delete(Invitation)
        .where(Invitation.token_hash == hash_token(payload.token), Invitation.expires_at > now)
        .returning(Invitation.email, Invitation.language)
    ).first()
    if invitation is None:
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)
    user = User(
        email=invitation.email,
        language=payload.language or invitation.language,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        email_verified_at=now,
    )
    db.add(user)
    try:
        add_onboarding_data(db, user)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=INVALID_INVITATION) from error
    return Message(message=localized("api.accountCreatedSignInWithYourEmailAndPassword"))
