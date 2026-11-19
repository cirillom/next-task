from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.i18n import localized
from app.models import Tag, Task, TaskBlock, User


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def block_is_active(block: TaskBlock, now: datetime | None = None) -> bool:
    if block.unblocked_at is None:
        return True
    current = now or datetime.now(UTC)
    return normalize_utc(block.unblocked_at) > current


def active_block_condition(now: datetime):
    return or_(TaskBlock.unblocked_at.is_(None), TaskBlock.unblocked_at > now)


def descendant_tasks(task: Task) -> list[Task]:
    descendants: list[Task] = []
    pending = list(task.subtasks)
    while pending:
        child = pending.pop()
        descendants.append(child)
        pending.extend(child.subtasks)
    return descendants


def unfinished_descendant_count(task: Task) -> int:
    return sum(
        descendant.finished_at is None and descendant.abandoned_by_task_id is None
        for descendant in descendant_tasks(task)
    )


def get_task_for_user(db: Session, task_id: int, user: User) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail=localized("api.taskNotFound"))
    return task


def validate_tags(db: Session, user_id: int, tag_ids: list[int]) -> list[Tag]:
    unique_ids = set(tag_ids)
    if not unique_ids:
        return []
    tags = list(
        db.scalars(select(Tag).where(Tag.id.in_(unique_ids)).order_by(Tag.name, Tag.id)).all()
    )
    if len(tags) != len(unique_ids) or any(tag.user_id != user_id for tag in tags):
        raise HTTPException(status_code=422, detail=localized("api.everyTagMustBelongToTheUser"))
    return tags


def validate_parent(
    db: Session, user_id: int, parent_id: int | None, task_id: int | None = None
) -> Task | None:
    if parent_id is None:
        return None
    if task_id is not None and parent_id == task_id:
        raise HTTPException(status_code=422, detail=localized("api.aTaskCannotParentItself"))
    parent = db.get(Task, parent_id)
    if parent is None or parent.user_id != user_id:
        raise HTTPException(status_code=422, detail=localized("api.parentTaskMustBelongToTheUser"))
    if task_id is None:
        return parent

    ancestors = (
        select(Task.parent_task_id.label("task_id"))
        .where(Task.id == parent_id, Task.parent_task_id.is_not(None))
        .cte(name="task_ancestors", recursive=True)
    )
    ancestors = ancestors.union(
        select(Task.parent_task_id)
        .join(ancestors, Task.id == ancestors.c.task_id)
        .where(Task.parent_task_id.is_not(None))
    )
    if task_id in set(db.scalars(select(ancestors.c.task_id)).all()):
        raise HTTPException(status_code=422, detail=localized("api.taskHierarchyWouldCreateACycle"))
    return parent
