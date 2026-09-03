from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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
from app.schemas import LoginRequest, Message, PasswordChange, UserRead

router = APIRouter(prefix="/api/auth", tags=["authentication"])


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
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(payload.email)))
    if user is None or not verify_password(user.password_hash, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
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
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Wrong password")
    user.password_hash = hash_password(payload.new_password)
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
