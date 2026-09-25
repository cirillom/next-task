from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import Tag, Task, User, WorkspaceMember
from app.pomodoro_models import PomodoroSession, PomodoroSettings
from app.pomodoro_schemas import (
    PomodoroSessionCreate,
    PomodoroSessionRead,
    PomodoroSessionTaskUpdate,
    PomodoroSettingsRead,
    PomodoroSettingsUpdate,
)

router = APIRouter(prefix="/api/pomodoro", tags=["pomodoro"])

DEFAULT_SETTINGS = PomodoroSettingsRead(
    focus_minutes=25,
    short_break_minutes=5,
    long_break_minutes=15,
    short_breaks_before_long=3,
    alert_mode="notification",
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _settings(db: Session, user_id: int) -> PomodoroSettingsRead:
    settings = db.scalar(select(PomodoroSettings).where(PomodoroSettings.user_id == user_id))
    if settings is None:
        return DEFAULT_SETTINGS
    return PomodoroSettingsRead.model_validate(settings, from_attributes=True)


def _duration(settings: PomodoroSettingsRead, phase: str) -> timedelta:
    if phase == "focus":
        minutes = settings.focus_minutes
    elif phase == "short-break":
        minutes = settings.short_break_minutes
    else:
        minutes = settings.long_break_minutes
    return timedelta(minutes=minutes)


def _advance(session: PomodoroSession, settings: PomodoroSettingsRead) -> None:
    if session.phase == "focus":
        if session.short_breaks_taken >= settings.short_breaks_before_long:
            session.phase = "long-break"
        else:
            session.phase = "short-break"
            session.short_breaks_taken += 1
    else:
        if session.phase == "long-break":
            session.short_breaks_taken = 0
        session.phase = "focus"
    session.state = "ready"
    session.ends_at = None


def _reconcile(
    db: Session, session: PomodoroSession, settings: PomodoroSettingsRead, now: datetime
) -> None:
    if session.state != "running" or session.ends_at is None or _utc(session.ends_at) > now:
        return
    if settings.alert_mode == "alarm":
        session.state = "ringing"
    else:
        _advance(session, settings)
    db.commit()
    db.refresh(session)


def _session_read(session: PomodoroSession, now: datetime) -> PomodoroSessionRead:
    values = {
        key: getattr(session, key)
        for key in (
            "workspace_id",
            "tag_id",
            "task_id",
            "phase",
            "state",
            "short_breaks_taken",
            "ends_at",
        )
    }
    return PomodoroSessionRead.model_validate({**values, "server_now": now})


def _get_session(db: Session, user_id: int) -> PomodoroSession | None:
    return db.scalar(select(PomodoroSession).where(PomodoroSession.user_id == user_id))


def _require_session(db: Session, user_id: int) -> PomodoroSession:
    session = _get_session(db, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="No active Pomodoro session")
    return session


def _validate_scope(
    db: Session, user_id: int, workspace_id: int, tag_id: int | None, task_id: int | None
) -> None:
    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if tag_id is not None:
        tag = db.scalar(select(Tag).where(Tag.id == tag_id, Tag.workspace_id == workspace_id))
        if tag is None:
            raise HTTPException(status_code=422, detail="Tag must belong to the session workspace")
    if task_id is not None:
        task = db.scalar(select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id))
        if task is None:
            raise HTTPException(status_code=422, detail="Task must belong to the session workspace")


@router.get("/settings", response_model=PomodoroSettingsRead)
def get_pomodoro_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PomodoroSettingsRead:
    return _settings(db, user.id)


@router.put("/settings", response_model=PomodoroSettingsRead)
def update_pomodoro_settings(
    payload: PomodoroSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PomodoroSettingsRead:
    settings = db.scalar(select(PomodoroSettings).where(PomodoroSettings.user_id == user.id))
    if settings is None:
        settings = PomodoroSettings(user_id=user.id, **payload.model_dump())
        db.add(settings)
    else:
        for key, value in payload.model_dump().items():
            setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return PomodoroSettingsRead.model_validate(settings, from_attributes=True)


@router.get("/session", response_model=PomodoroSessionRead | None)
def get_pomodoro_session(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PomodoroSessionRead | None:
    session = _get_session(db, user.id)
    if session is None:
        return None
    now = datetime.now(UTC)
    _reconcile(db, session, _settings(db, user.id), now)
    return _session_read(session, now)


@router.post("/session", response_model=PomodoroSessionRead, status_code=status.HTTP_201_CREATED)
def create_pomodoro_session(
    payload: PomodoroSessionCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PomodoroSessionRead:
    existing = _get_session(db, user.id)
    now = datetime.now(UTC)
    if existing is not None:
        _reconcile(db, existing, _settings(db, user.id), now)
        response.status_code = status.HTTP_200_OK
        return _session_read(existing, now)

    _validate_scope(db, user.id, payload.workspace_id, payload.tag_id, payload.task_id)
    session = PomodoroSession(user_id=user.id, **payload.model_dump())
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _require_session(db, user.id)
        response.status_code = status.HTTP_200_OK
        return _session_read(existing, datetime.now(UTC))
    db.refresh(session)
    return _session_read(session, now)


@router.put("/session/task", response_model=PomodoroSessionRead)
def update_pomodoro_session_task(
    payload: PomodoroSessionTaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PomodoroSessionRead:
    session = _require_session(db, user.id)
    _validate_scope(db, user.id, session.workspace_id, session.tag_id, payload.task_id)
    session.task_id = payload.task_id
    db.commit()
    db.refresh(session)
    return _session_read(session, datetime.now(UTC))


@router.post("/session/start", response_model=PomodoroSessionRead)
def start_pomodoro_period(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PomodoroSessionRead:
    session = _require_session(db, user.id)
    settings = _settings(db, user.id)
    now = datetime.now(UTC)
    _reconcile(db, session, settings, now)
    if session.state != "ready":
        return _session_read(session, now)
    session.state = "running"
    session.ends_at = now + _duration(settings, session.phase)
    db.commit()
    db.refresh(session)
    return _session_read(session, now)


@router.post("/session/skip", response_model=PomodoroSessionRead)
def skip_pomodoro_period(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PomodoroSessionRead:
    session = _require_session(db, user.id)
    if session.state == "ringing":
        raise HTTPException(status_code=409, detail="Dismiss the alarm before continuing")
    _advance(session, _settings(db, user.id))
    db.commit()
    db.refresh(session)
    return _session_read(session, datetime.now(UTC))


@router.post("/session/dismiss", response_model=PomodoroSessionRead)
def dismiss_pomodoro_alarm(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PomodoroSessionRead:
    session = _require_session(db, user.id)
    if session.state == "ringing":
        _advance(session, _settings(db, user.id))
        db.commit()
        db.refresh(session)
    return _session_read(session, datetime.now(UTC))


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def delete_pomodoro_session(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    session = _get_session(db, user.id)
    if session is not None:
        db.delete(session)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
