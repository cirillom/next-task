from sqlalchemy import CheckConstraint, ForeignKey, Integer
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
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    focus_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    short_break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    long_break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    short_breaks_before_long: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
