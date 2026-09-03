from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag, Task, TaskStatus, User, WorkspaceMember


def get_task_for_user(db: Session, task_id: int, user: User) -> Task:
    task = db.get(Task, task_id)
    if task is None or db.get(WorkspaceMember, (user.id, task.workspace_id)) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def validate_status(db: Session, workspace_id: int, status_id: int) -> TaskStatus:
    item = db.get(TaskStatus, status_id)
    if item is None or item.workspace_id != workspace_id:
        raise HTTPException(status_code=422, detail="Status must belong to the task workspace")
    return item


def validate_assignees(db: Session, workspace_id: int, user_ids: list[int]) -> list[User]:
    unique_ids = set(user_ids)
    if not unique_ids:
        return []
    member_ids = set(
        db.scalars(
            select(WorkspaceMember.user_id).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id.in_(unique_ids),
            )
        ).all()
    )
    if member_ids != unique_ids:
        raise HTTPException(status_code=422, detail="Every assignee must be a workspace member")
    return list(db.scalars(select(User).where(User.id.in_(unique_ids)).order_by(User.id)).all())


def validate_tags(db: Session, workspace_id: int, tag_ids: list[int]) -> list[Tag]:
    unique_ids = set(tag_ids)
    if not unique_ids:
        return []
    tags = list(db.scalars(select(Tag).where(Tag.id.in_(unique_ids)).order_by(Tag.name)).all())
    if len(tags) != len(unique_ids) or any(tag.workspace_id != workspace_id for tag in tags):
        raise HTTPException(status_code=422, detail="Every tag must belong to the task workspace")
    return tags


def validate_parent(
    db: Session, workspace_id: int, parent_id: int | None, task_id: int | None = None
) -> Task | None:
    if parent_id is None:
        return None
    if task_id is not None and parent_id == task_id:
        raise HTTPException(status_code=422, detail="A task cannot parent itself")
    parent = db.get(Task, parent_id)
    if parent is None or parent.workspace_id != workspace_id:
        raise HTTPException(status_code=422, detail="Parent task must belong to the same workspace")
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
        raise HTTPException(status_code=422, detail="Task hierarchy would create a cycle")
    return parent
