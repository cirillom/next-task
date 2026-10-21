from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.rate_limit import (
    ACCOUNT_FAILURE_LIMIT,
    IP_BURST_LIMIT,
    IP_BURST_WINDOW,
    IP_FAILURE_LIMIT,
    IP_FAILURE_WINDOW,
    LOCKOUT,
    PASSWORD_CHANGE_FAILURE_LIMIT,
    WINDOW,
    account_key,
    clear_attempts,
    ip_burst_key,
    ip_key,
    is_locked,
    lock_window_if_full,
    password_change_key,
    purge_expired_attempts,
    record_attempt,
    release_window_attempt,
    reserve_window_attempt,
)
from app.auth.security import (
    create_session,
    current_session,
    get_current_user,
    hash_password,
    normalize_email,
    session_token_hash,
    verify_password,
)
from app.config import get_settings
from app.database import get_db
from app.models import User, UserSession
from app.schemas import LoginRequest, Message, PasswordChange, SignUpRequest, UserRead

router = APIRouter(prefix="/api/auth", tags=["authentication"])
DUMMY_PASSWORD_HASH = hash_password("this is a dummy password used for unknown accounts")
INVALID_LOGIN = "Invalid username/email or password"


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def default_display_name(identifier: str) -> str:
    name = identifier.split("@", 1)[0] if "@" in identifier else identifier
    return name[:160]


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def signup(payload: SignUpRequest, response: Response, db: Session = Depends(get_db)) -> User:
    identifier = normalize_email(payload.identifier)
    user = User(
        email=identifier,
        display_name=default_display_name(identifier),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That username or email is already in use",
        ) from error
    db.refresh(user)
    token, _expires_at = create_session(db, user)
    set_session_cookie(response, token)
    return user


@router.post("/login", response_model=UserRead)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    now = datetime.now(UTC)
    purge_expired_attempts(db, now)
    client_ip = request.client.host if request.client is not None else "unknown"
    if (
        reserve_window_attempt(
            db, ip_burst_key(client_ip), now, window=IP_BURST_WINDOW, limit=IP_BURST_LIMIT
        )
        is None
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
        )
    ip_failure_attempt = reserve_window_attempt(
        db, ip_key(client_ip), now, window=IP_FAILURE_WINDOW, limit=IP_FAILURE_LIMIT
    )
    if ip_failure_attempt is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
        )

    user = db.scalar(select(User).where(User.email == normalize_email(payload.email)))
    key = account_key(user.id) if user is not None else None
    locked = key is not None and is_locked(db, key, now)
    account_attempt = None
    if key is not None and not locked:
        account_attempt = reserve_window_attempt(
            db, key, now, window=WINDOW, limit=ACCOUNT_FAILURE_LIMIT
        )
        locked = account_attempt is None
    password_hash = user.password_hash if user is not None and not locked else DUMMY_PASSWORD_HASH
    valid_password = verify_password(password_hash, payload.password)
    if user is None or locked or not valid_password:
        if key is not None and account_attempt is not None and not valid_password:
            lock_window_if_full(
                db, key, now, window=WINDOW, limit=ACCOUNT_FAILURE_LIMIT, lockout=LOCKOUT
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_LOGIN,
        )
    release_window_attempt(db, ip_failure_attempt)
    clear_attempts(db, key)
    token, _expires_at = create_session(db, user)
    set_session_cookie(response, token)
    return user


@router.post("/logout", response_model=Message)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Message:
    token = request.cookies.get(get_settings().session_cookie_name)
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == session_token_hash(token)))
        db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return Message(message="Logged out")


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password", response_model=Message)
def change_password(
    payload: PasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Message:
    now = datetime.now(UTC)
    key = password_change_key(user.id)
    if is_locked(db, key, now):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Could not change password"
        )
    if (
        record_attempt(db, key, now, limit=PASSWORD_CHANGE_FAILURE_LIMIT, lockout=LOCKOUT)
        > PASSWORD_CHANGE_FAILURE_LIMIT
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Could not change password"
        )
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Could not change password"
        )
    user.password_hash = hash_password(payload.new_password)
    clear_attempts(db, key)
    session = current_session(request, db)
    if session is not None:
        db.execute(
            delete(UserSession).where(
                UserSession.user_id == user.id,
                UserSession.token_hash != session.token_hash,
            )
        )
    db.commit()
    return Message(message="Password changed")
