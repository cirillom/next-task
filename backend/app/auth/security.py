import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User, UserSession

password_hasher = PasswordHasher()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(days=get_settings().session_ttl_days)
    token = secrets.token_urlsafe(32)
    db.execute(delete(UserSession).where(UserSession.expires_at < datetime.now(UTC)))
    db.add(
        UserSession(token_hash=session_token_hash(token), user_id=user.id, expires_at=expires_at)
    )
    db.commit()
    return token, expires_at


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def current_session(request: Request, db: Session) -> UserSession | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == session_token_hash(token))
    )
    if session is None:
        return None
    if _as_utc(session.expires_at) <= datetime.now(UTC):
        db.delete(session)
        db.commit()
        return None
    return session


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    session = current_session(request, db)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return session.user
