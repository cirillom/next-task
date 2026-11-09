"""Email recovery changes the password; it never creates a signed-in session."""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.rate_limit import ip_key, purge_expired_attempts, reserve_window_attempt
from app.auth.security import hash_token, normalize_email, replace_password
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import PasswordReset, User
from app.schemas import Message, PasswordResetConfirm, PasswordResetRequest
from app.services.mail import MailDeliveryError, public_app_url, send_email

router = APIRouter(prefix="/api/auth", tags=["authentication"])
logger = logging.getLogger(__name__)
RESET_LIFETIME = timedelta(minutes=30)
RESET_WINDOW = timedelta(minutes=15)
RESET_IP_LIMIT = 10
RESET_EMAIL_LIMIT = 3
RESET_TOKEN_LIMIT = 10
RESET_REQUESTED = (
    "If this address belongs to a verified account, you'll receive a password reset link."
)
INVALID_RESET = "This reset link is invalid or expired. Request a new link."


def credential_hash(user: User) -> str:
    # Also invalidate a link if credentials change while SMTP delivery is in flight.
    return hash_token(f"{user.password_hash}:{user.email}:{user.email_verified_at}")


def send_reset_link(email: str) -> None:
    try:
        with SessionLocal() as db:
            user = db.scalar(
                select(User).where(User.email == email, User.email_verified_at.is_not(None))
            )
            if user is None:
                return
            token = secrets.token_urlsafe(32)
            fingerprint = credential_hash(user)
            link = f"{public_app_url()}/#/reset-password?token={token}"
            send_email(
                email,
                "Reset your Next Task password",
                "Use this link to choose a new password. It expires in 30 minutes and works once. "
                "If you did not request this, ignore this email.\n\n"
                f"{link}\n",
            )
            # Persist only after SMTP accepts the message. Failed delivery keeps the old link.
            insert = postgres_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
            statement = insert(PasswordReset).values(
                user_id=user.id,
                email=email,
                credential_hash=fingerprint,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + RESET_LIFETIME,
            )
            db.execute(
                statement.on_conflict_do_update(
                    index_elements=[PasswordReset.user_id],
                    set_={
                        name: getattr(statement.excluded, name)
                        for name in ("email", "credential_hash", "token_hash", "expires_at")
                    },
                )
            )
            db.commit()
    except (ValueError, MailDeliveryError, SQLAlchemyError) as error:
        logger.error("Password reset delivery failed (%s)", type(error).__name__)


def notify_password_reset(email: str) -> None:
    try:
        send_email(
            email,
            "Your Next Task password was changed",
            "Your password was reset and all devices were signed out. "
            "If you did not make this change, contact your Next Task administrator.\n",
        )
    except (ValueError, MailDeliveryError) as error:
        logger.error("Password reset notification failed (%s)", type(error).__name__)


def limit_ip(db: Session, request: Request, action: str, now: datetime, limit: int) -> None:
    purge_expired_attempts(db, now)
    client_ip = request.client.host if request.client else "unknown"
    if (
        reserve_window_attempt(
            db, f"reset-{action}:{ip_key(client_ip)}", now, window=RESET_WINDOW, limit=limit
        )
        is None
    ):
        raise HTTPException(status_code=429, detail="Too many recovery attempts. Try again later.")


@router.post("/forgot-password", response_model=Message, status_code=202)
def forgot_password(
    payload: PasswordResetRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Message:
    now = datetime.now(UTC)
    limit_ip(db, request, "request", now, RESET_IP_LIMIT)
    email = normalize_email(payload.email)
    if (
        reserve_window_attempt(
            db,
            f"reset-email:{hash_token(email)}",
            now,
            window=RESET_WINDOW,
            limit=RESET_EMAIL_LIMIT,
        )
        is not None
    ):
        # Lookup and SMTP run after the response, for both existing and unknown addresses.
        background.add_task(send_reset_link, email)
    return Message(message=RESET_REQUESTED)


@router.post("/reset-password", response_model=Message)
def reset_password(
    payload: PasswordResetConfirm,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Message:
    now = datetime.now(UTC)
    limit_ip(db, request, "token", now, RESET_TOKEN_LIMIT)
    consumed = db.execute(
        delete(PasswordReset)
        .where(
            PasswordReset.token_hash == hash_token(payload.token), PasswordReset.expires_at > now
        )
        .returning(PasswordReset.user_id, PasswordReset.email, PasswordReset.credential_hash)
    ).first()
    if consumed is None:
        raise HTTPException(status_code=400, detail=INVALID_RESET)
    user = db.get(User, consumed.user_id)
    if (
        user is None
        or user.email_verified_at is None
        or user.email != consumed.email
        or credential_hash(user) != consumed.credential_hash
    ):
        raise HTTPException(status_code=400, detail=INVALID_RESET)
    replace_password(db, user, payload.new_password)
    db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    background.add_task(notify_password_reset, user.email)
    return Message(message="Password changed. Sign in with your new password.")
