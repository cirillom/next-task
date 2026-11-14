"""Starter data for new accounts, committed together with their owner."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.i18n import translate
from app.models import Tag, TagRelationship, Task, TaskBlock, User
from app.services.scoring import DEFAULT_SCORING_FORMULA


def add_onboarding_data(db: Session, user: User) -> None:
    """Call only during account creation; the caller owns commit and rollback."""
    db.flush()
    created_at = user.created_at
    creation_date = created_at.astimezone().date()
    tags: dict[str, Tag] = {}
    for name, parent, value, color in (
        ("personal", None, 0, "#3F7D63"),
        ("routine", "personal", 0, None),
        ("learning", "personal", 1, None),
        ("work", None, 0, "#4C79A8"),
        ("projects", "work", 1, None),
        ("admin", "work", 0, None),
        ("urgent", None, 5, "#D64545"),
    ):
        tag = Tag(
            user_id=user.id,
            name=translate(f"onboarding.tag.{name}.name", user.language),
            score_value=value,
            color=tags[parent].color if parent else color,
            description=translate(f"onboarding.tag.{name}.description", user.language),
        )
        db.add(tag)
        tags[name] = tag
        if parent:
            db.add(TagRelationship(child=tag, parent=tags[parent]))

    previous: Task | None = None
    for step, priority, tag, due_days in (
        ("1", 4, "learning", None),
        ("2", 3, "projects", None),
        ("3", 2, "routine", 7),
        ("4", 1, "learning", None),
    ):
        task = Task(
            user_id=user.id,
            title=translate(f"onboarding.task.{step}.title", user.language),
            description=translate(
                f"onboarding.task.{step}.description",
                user.language,
                formula=DEFAULT_SCORING_FORMULA,
            ),
            priority=priority,
            tags=[tags[tag]],
            due_date=creation_date + timedelta(days=due_days) if due_days else None,
            created_at=created_at,
            updated_at=created_at,
        )
        db.add(task)
        if previous is not None:
            db.add(TaskBlock(task=task, blocking_task=previous, blocked_at=created_at))
        previous = task
