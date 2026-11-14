import logging
import secrets
from datetime import UTC, datetime, timedelta

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
    hash_token,
    normalize_email,
    replace_password,
    verify_password,
)
from app.config import get_settings
from app.database import get_db
from app.i18n import error_detail, localized, translate
from app.models import EmailVerification, PasswordReset, User, UserSession
from app.schemas import (
    EmailRequest,
    EmailStatus,
    LanguageUpdate,
    LoginRequest,
    Message,
    PasswordChange,
    TokenRequest,
    UserRead,
    ensure_utc,
)
from app.services.mail import (
    MailConfigurationError,
    MailDeliveryError,
    public_app_url,
    send_email,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
logger = logging.getLogger(__name__)
DUMMY_PASSWORD_HASH = hash_password("this is a dummy password used for unknown accounts")
INVALID_LOGIN = localized("api.invalidEmailOrPassword")
VERIFICATION_LIFETIME = timedelta(hours=24)
VERIFICATION_RESEND_WAIT = timedelta(seconds=60)


def require_current_password(
    db: Session, user: User, password: str, key: str, now: datetime, detail: str
) -> None:
    if (
        is_locked(db, key, now)
        or record_attempt(db, key, now, limit=PASSWORD_CHANGE_FAILURE_LIMIT, lockout=LOCKOUT)
        > PASSWORD_CHANGE_FAILURE_LIMIT
        or not verify_password(user.password_hash, password)
    ):
        raise HTTPException(status_code=400, detail=detail)
    clear_attempts(db, key)


def email_status(user: User, now: datetime) -> EmailStatus:
    pending = user.email_verification
    active = pending is not None and ensure_utc(pending.expires_at) > now
    return EmailStatus(
        verified=user.email_verified_at is not None,
        pending_email=pending.email if active else None,
    )


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
            detail=localized("api.tooManyAuthenticationAttemptsTryAgainLater"),
        )
    ip_failure_attempt = reserve_window_attempt(
        db, ip_key(client_ip), now, window=IP_FAILURE_WINDOW, limit=IP_FAILURE_LIMIT
    )
    if ip_failure_attempt is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=localized("api.tooManyAuthenticationAttemptsTryAgainLater"),
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
        db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
        db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return Message(message=localized("api.loggedOut"))


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.put("/language", response_model=UserRead)
def change_language(
    payload: LanguageUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    user.language = payload.language
    db.commit()
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
    require_current_password(
        db,
        user,
        payload.current_password,
        key,
        now,
        localized("ui.settings.couldNotChangePassword"),
    )
    session = current_session(request, db)
    replace_password(db, user, payload.new_password, session.token_hash if session else None)
    db.commit()
    return Message(message=localized("api.passwordChanged"))


@router.get("/email", response_model=EmailStatus)
def get_email(user: User = Depends(get_current_user)) -> EmailStatus:
    return email_status(user, datetime.now(UTC))


@router.post("/email", response_model=EmailStatus)
def request_email(
    payload: EmailRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EmailStatus:
    now = datetime.now(UTC)
    key = f"email-update:{user.id}"
    require_current_password(
        db, user, payload.current_password, key, now, localized("api.couldNotUpdateEmail")
    )
    db.commit()

    email = payload.email
    if db.scalar(select(User.id).where(User.id != user.id, User.email == email)) is not None:
        raise HTTPException(status_code=409, detail=localized("api.thatEmailIsAlreadyInUse"))

    pending = user.email_verification
    if email == user.email and user.email_verified_at:
        if pending is not None:
            user.email_verification = None
            db.commit()
        return email_status(user, now)
    send_attempt = reserve_window_attempt(
        db,
        f"email-send:{user.id}",
        now,
        window=VERIFICATION_RESEND_WAIT,
        limit=1,
    )
    if send_attempt is None:
        raise HTTPException(
            status_code=429, detail=localized("api.waitOneMinuteBeforeSendingAnotherEmail")
        )

    token = secrets.token_urlsafe(32)
    if pending is None:
        pending = EmailVerification()
        user.email_verification = pending
    pending.email = email
    pending.token_hash = hash_token(token)
    pending.expires_at = now + VERIFICATION_LIFETIME
    try:
        url = public_app_url()
        link = f"{url}/#/verify-email?token={token}&lang={user.language}"
        send_email(
            email,
            translate("mail.verifySubject", user.language),
            translate("mail.verifyBody", user.language, link=link),
        )
        db.commit()
    except (MailConfigurationError, MailDeliveryError) as error:
        db.rollback()
        release_window_attempt(db, send_attempt)
        if isinstance(error, MailConfigurationError):
            logger.error("Email configuration failed: %s", error)
            raise HTTPException(
                status_code=503,
                detail=localized("api.emailVerificationIsUnavailableCheckTheServerSEmail"),
            ) from error
        raise HTTPException(status_code=503, detail=error_detail(error)) from error
    return email_status(user, now)


@router.post("/email/verify", response_model=Message)
def verify_email(payload: TokenRequest, db: Session = Depends(get_db)) -> Message:
    now = datetime.now(UTC)
    token_hash = hash_token(payload.token)
    consumed = db.execute(
        delete(EmailVerification)
        .where(EmailVerification.token_hash == token_hash, EmailVerification.expires_at > now)
        .returning(EmailVerification.user_id, EmailVerification.email)
    ).first()
    if consumed is None:
        raise HTTPException(
            status_code=400, detail=localized("api.verificationLinkIsInvalidOrExpired")
        )
    user_id, email = consumed
    user = db.get(User, user_id)
    if user is None:
        db.rollback()
        raise HTTPException(
            status_code=400, detail=localized("api.verificationLinkIsInvalidOrExpired")
        )
    try:
        user.email = email
        user.email_verified_at = now
        db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=localized("api.thatEmailIsAlreadyInUse")
        ) from error
    return Message(message=localized("ui.accountSettings.emailVerified"))
