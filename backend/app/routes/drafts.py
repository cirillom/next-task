from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import Task, TaskStatus, User
from app.routes.tasks import apply_task_relations, task_read
from app.schemas import TaskRead, TaskUpdate
from app.services.tasks import validate_parent, validate_status
from app.services.workspaces import get_membership, require_editor

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


class DraftCreate(TaskUpdate):
    workspace_id: int
    title: str = Field(min_length=1, max_length=500)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be blank")
        return cleaned


@router.get("", response_model=list[TaskRead])
def list_drafts(
    workspace_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TaskRead]:
    get_membership(db, workspace_id, user.id)
    drafts = list(
        db.scalars(
            select(Task)
            .where(
                Task.workspace_id == workspace_id,
                Task.priority == 0,
                Task.finished_at.is_(None),
            )
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
        .unique()
        .all()
    )
    return [task_read(db, task) for task in drafts]


@router.post("", response_model=TaskRead, status_code=201)
def create_draft(
    payload: DraftCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskRead:
    require_editor(db, payload.workspace_id, user)
    status_id = payload.status_id
    if status_id is None:
        default_status = db.scalar(
            select(TaskStatus)
            .where(TaskStatus.workspace_id == payload.workspace_id)
            .order_by(TaskStatus.id)
            .limit(1)
        )
        if default_status is None:
            raise HTTPException(
                status_code=422, detail="Workspace needs a task status before drafting"
            )
        status_id = default_status.id
    validate_status(db, payload.workspace_id, status_id)
    validate_parent(db, payload.workspace_id, payload.parent_task_id)

    values = payload.model_dump(
        exclude={"workspace_id", "priority", "status_id", "assignee_ids", "tag_ids"}
    )
    task = Task(
        created_by_user_id=user.id,
        workspace_id=payload.workspace_id,
        status_id=status_id,
        priority=0,
        **values,
    )
    db.add(task)
    db.flush()
    apply_task_relations(db, task, payload.assignee_ids, payload.tag_ids)
    db.commit()
    db.refresh(task)
    return task_read(db, task)
