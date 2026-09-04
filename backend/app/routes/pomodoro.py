from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import User
from app.pomodoro_models import PomodoroSettings
from app.pomodoro_schemas import PomodoroSettingsRead, PomodoroSettingsUpdate

router = APIRouter(prefix="/api/pomodoro", tags=["pomodoro"])

DEFAULT_SETTINGS = PomodoroSettingsRead(
    focus_minutes=25,
    short_break_minutes=5,
    long_break_minutes=15,
    short_breaks_before_long=3,
)


@router.get("/settings", response_model=PomodoroSettingsRead)
def get_pomodoro_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PomodoroSettingsRead:
    settings = db.scalar(select(PomodoroSettings).where(PomodoroSettings.user_id == user.id))
    if settings is None:
        return DEFAULT_SETTINGS
    return PomodoroSettingsRead.model_validate(settings, from_attributes=True)


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
