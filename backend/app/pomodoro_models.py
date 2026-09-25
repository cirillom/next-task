from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PomodoroSettings(Base):
    __tablename__ = "pomodoro_settings"
    __table_args__ = (
        CheckConstraint("focus_minutes BETWEEN 1 AND 180", name="pomodoro_focus_minutes_range"),
        CheckConstraint(
            "short_break_minutes BETWEEN 1 AND 60", name="pomodoro_short_break_minutes_range"
        ),
        CheckConstraint(
            "long_break_minutes BETWEEN 1 AND 180", name="pomodoro_long_break_minutes_range"
        ),
        CheckConstraint(
            "short_breaks_before_long BETWEEN 1 AND 12",
            name="pomodoro_short_breaks_before_long_range",
        ),
        CheckConstraint(
            "alert_mode IN ('notification', 'alarm')", name="pomodoro_alert_mode"
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    focus_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    short_break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    long_break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    short_breaks_before_long: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    alert_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="notification", server_default="notification"
    )


class PomodoroSession(Base):
    __tablename__ = "pomodoro_sessions"
    __table_args__ = (
        CheckConstraint(
            "phase IN ('focus', 'short-break', 'long-break')", name="pomodoro_session_phase"
        ),
        CheckConstraint(
            "state IN ('ready', 'running', 'ringing')", name="pomodoro_session_state"
        ),
        CheckConstraint("short_breaks_taken >= 0", name="pomodoro_short_breaks_taken_positive"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[int | None] = mapped_column(
        ForeignKey("tags.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    phase: Mapped[str] = mapped_column(String(20), nullable=False, default="focus")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")
    short_breaks_taken: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
