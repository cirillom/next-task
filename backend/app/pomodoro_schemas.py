from pydantic import BaseModel, Field


class PomodoroSettingsRead(BaseModel):
    focus_minutes: int
    short_break_minutes: int
    long_break_minutes: int
    short_breaks_before_long: int


class PomodoroSettingsUpdate(BaseModel):
    focus_minutes: int = Field(ge=1, le=180)
    short_break_minutes: int = Field(ge=1, le=60)
    long_break_minutes: int = Field(ge=1, le=180)
    short_breaks_before_long: int = Field(ge=1, le=12)
