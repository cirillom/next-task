from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import Tag, Task, TaskAssignee, TaskBlock, User
from app.schemas import (
    BlockCreate,
    BlockRead,
    TagSummary,
    TaskCreate,
    TaskRead,
    TaskSummary,
    TaskUpdate,
    UserRead,
)
from app.services.scoring import score_task
from app.services.tags import ancestor_ids, descendant_ids, tags_by_ids
from app.services.tasks import (
    get_task_for_user,
    validate_assignees,
    validate_parent,
    validate_status,
    validate_tags,
)
from app.services.workspaces import get_membership, require_editor

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def task_read(db: Session, task: Task) -> TaskRead:
    direct_ids = {tag.id for tag in task.tags}
    inherited = tags_by_ids(db, ancestor_ids(db, direct_ids) - direct_ids)
    current_block = next((block for block in task.blocks if block.unblocked_at is None), None)
    return TaskRead(
        id=task.id,
        created_by_user_id=task.created_by_user_id,
        creator=UserRead.model_validate(task.creator),
        workspace_id=task.workspace_id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date,
        last_worked_at=task.last_worked_at,
        finished_at=task.finished_at,
        parent_task_id=task.parent_task_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
        score=round(score_task(task), 2),
        assignees=[UserRead.model_validate(user) for user in task.assignees],
        direct_tags=[TagSummary.model_validate(tag) for tag in task.tags],
        inherited_tags=[TagSummary.model_validate(tag) for tag in inherited],
        current_block=BlockRead.model_validate(current_block) if current_block else None,
        blocking_history=[BlockRead.model_validate(block) for block in task.blocks],
        subtasks=[TaskSummary.model_validate(subtask) for subtask in task.subtasks],
    )


def apply_task_relations(
    db: Session,
    task: Task,
    assignee_ids: list[int] | None,
    tag_ids: list[int] | None,
) -> None:
    if assignee_ids is not None:
        task.assignees = validate_assignees(db, task.workspace_id, assignee_ids)
    if tag_ids is not None:
        task.tags = validate_tags(db, task.workspace_id, tag_ids)


@router.get("", response_model=list[TaskRead])
def list_tasks(
    workspace_id: int,
    finished: bool | None = False,
    status_id: int | None = None,
    tag_id: int | None = None,
    assignee_id: int | None = None,
    blocked: bool | None = None,
    search: str | None = Query(default=None, max_length=300),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TaskRead]:
    get_membership(db, workspace_id, user.id)
    query = select(Task).where(Task.workspace_id == workspace_id)
    if finished is True:
        query = query.where(Task.finished_at.is_not(None))
    elif finished is False:
        query = query.where(Task.finished_at.is_(None))
    if status_id is not None:
        query = query.where(Task.status_id == status_id)
    if assignee_id is not None:
        query = query.where(
            exists().where(TaskAssignee.task_id == Task.id, TaskAssignee.user_id == assignee_id)
        )
    if tag_id is not None:
        allowed_tag_ids = descendant_ids(db, tag_id)
        query = query.where(Task.tags.any(Tag.id.in_(allowed_tag_ids)))
    if blocked is not None:
        active_block = exists().where(
            TaskBlock.task_id == Task.id, TaskBlock.unblocked_at.is_(None)
        )
        query = query.where(active_block if blocked else ~active_block)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))
    tasks = list(db.scalars(query.order_by(Task.created_at.desc())).unique().all())
    result = [task_read(db, task) for task in tasks]
    return sorted(result, key=lambda item: (-item.score, item.id))


@router.post("", response_model=TaskRead, status_code=201)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskRead:
    require_editor(db, payload.workspace_id, user)
    validate_status(db, payload.workspace_id, payload.status_id)
    validate_parent(db, payload.workspace_id, payload.parent_task_id)
    values = payload.model_dump(exclude={"assignee_ids", "tag_ids"})
    task = Task(created_by_user_id=user.id, **values)
    db.add(task)
    db.flush()
    apply_task_relations(db, task, payload.assignee_ids, payload.tag_ids)
    db.commit()
    db.refresh(task)
    return task_read(db, task)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskRead:
    return task_read(db, get_task_for_user(db, task_id, user))


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskRead:
    task = get_task_for_user(db, task_id, user)
    require_editor(db, task.workspace_id, user)
    values = payload.model_dump(exclude_unset=True)
    if "status_id" in values:
        if values["status_id"] is None:
            raise HTTPException(status_code=422, detail="A task must have a status")
        validate_status(db, task.workspace_id, values["status_id"])
    if "parent_task_id" in values:
        validate_parent(db, task.workspace_id, values["parent_task_id"], task.id)
    apply_task_relations(db, task, values.pop("assignee_ids", None), values.pop("tag_ids", None))
    for key, value in values.items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task_read(db, task)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    task = get_task_for_user(db, task_id, user)
    require_editor(db, task.workspace_id, user)
    db.delete(task)
    db.commit()
    return Response(status_code=204)


@router.post("/{task_id}/finish", response_model=TaskRead)
def finish_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskRead:
    task = get_task_for_user(db, task_id, user)
    require_editor(db, task.workspace_id, user)
    if task.finished_at is None:
        task.finished_at = datetime.now(UTC)
        db.commit()
    return task_read(db, task)


@router.post("/{task_id}/reopen", response_model=TaskRead)
def reopen_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskRead:
    task = get_task_for_user(db, task_id, user)
    require_editor(db, task.workspace_id, user)
    if task.finished_at is not None:
        task.finished_at = None
        db.commit()
    return task_read(db, task)


@router.post("/{task_id}/block", response_model=TaskRead, status_code=201)
def block_task(
    task_id: int,
    payload: BlockCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskRead:
    task = get_task_for_user(db, task_id, user)
    require_editor(db, task.workspace_id, user)
    db.add(TaskBlock(task_id=task.id, reason=payload.reason))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Task is already blocked") from error
    db.refresh(task)
    return task_read(db, task)


@router.post("/{task_id}/unblock", response_model=TaskRead)
def unblock_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskRead:
    task = get_task_for_user(db, task_id, user)
    require_editor(db, task.workspace_id, user)
    active = db.scalar(
        select(TaskBlock).where(TaskBlock.task_id == task.id, TaskBlock.unblocked_at.is_(None))
    )
    if active is None:
        raise HTTPException(status_code=409, detail="Task is not blocked")
    active.unblocked_at = datetime.now(UTC)
    db.commit()
    db.refresh(task)
    return task_read(db, task)
