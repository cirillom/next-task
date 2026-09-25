from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import UtcDateTime

PomodoroAlertMode = Literal["notification", "alarm"]
PomodoroPhase = Literal["focus", "short-break", "long-break"]
PomodoroState = Literal["ready", "running", "ringing"]


class PomodoroSettingsRead(BaseModel):
    focus_minutes: int
    short_break_minutes: int
    long_break_minutes: int
    short_breaks_before_long: int
    alert_mode: PomodoroAlertMode


class PomodoroSettingsUpdate(BaseModel):
    focus_minutes: int = Field(ge=1, le=180)
    short_break_minutes: int = Field(ge=1, le=60)
    long_break_minutes: int = Field(ge=1, le=180)
    short_breaks_before_long: int = Field(ge=1, le=12)
    alert_mode: PomodoroAlertMode


class PomodoroSessionCreate(BaseModel):
    workspace_id: int
    tag_id: int | None = None
    task_id: int | None = None


class PomodoroSessionTaskUpdate(BaseModel):
    task_id: int | None = None


class PomodoroSessionRead(BaseModel):
    workspace_id: int
    tag_id: int | None
    task_id: int | None
    phase: PomodoroPhase
    state: PomodoroState
    short_breaks_taken: int
    ends_at: UtcDateTime | None
    server_now: datetime
