from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import get_current_user, normalize_email
from app.database import get_db
from app.models import (
    Task,
    TaskAssignee,
    TaskStatus,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)
from app.schemas import (
    MemberCreate,
    MemberRead,
    MemberUpdate,
    StatusCreate,
    StatusRead,
    StatusUpdate,
    WorkspaceCreate,
    WorkspaceRead,
    WorkspaceUpdate,
)
from app.services.scoring import DEFAULT_SCORING_FORMULA, FormulaError, validate_formula
from app.services.workspaces import (
    ensure_owner_remains,
    get_membership,
    require_editor,
    require_owner,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def workspace_read(workspace: Workspace, role: WorkspaceRole) -> WorkspaceRead:
    return WorkspaceRead(
        id=workspace.id,
        name=workspace.name,
        scoring_formula=workspace.scoring_formula,
        created_at=workspace.created_at,
        role=role,
    )


@router.get("", response_model=list[WorkspaceRead])
def list_workspaces(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[WorkspaceRead]:
    memberships = db.scalars(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(WorkspaceMember.workspace_id)
    ).all()
    return [workspace_read(item.workspace, item.role) for item in memberships]


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorkspaceRead:
    workspace = Workspace(name=payload.name, scoring_formula=DEFAULT_SCORING_FORMULA)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(user_id=user.id, workspace_id=workspace.id, role=WorkspaceRole.OWNER))
    db.add_all(
        [
            TaskStatus(workspace_id=workspace.id, name="todo", score_value=0),
            TaskStatus(workspace_id=workspace.id, name="doing", score_value=1),
        ]
    )
    db.commit()
    db.refresh(workspace)
    return workspace_read(workspace, WorkspaceRole.OWNER)


@router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorkspaceRead:
    membership = get_membership(db, workspace_id, user.id)
    return workspace_read(membership.workspace, membership.role)


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
def update_workspace(
    workspace_id: int,
    payload: WorkspaceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorkspaceRead:
    membership = require_owner(db, workspace_id, user)
    values = payload.model_dump(exclude_unset=True)
    if values.get("scoring_formula") is not None:
        try:
            validate_formula(values["scoring_formula"])
        except FormulaError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    for key, value in values.items():
        setattr(membership.workspace, key, value)
    db.commit()
    db.refresh(membership.workspace)
    return workspace_read(membership.workspace, membership.role)


@router.get("/{workspace_id}/members", response_model=list[MemberRead])
def list_members(
    workspace_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MemberRead]:
    get_membership(db, workspace_id, user.id)
    memberships = db.scalars(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.user_id)
    ).all()
    return [
        MemberRead(
            user_id=item.user_id,
            email=item.user.email,
            display_name=item.user.display_name,
            role=item.role,
        )
        for item in memberships
    ]


@router.post("/{workspace_id}/members", response_model=MemberRead, status_code=201)
def add_member(
    workspace_id: int,
    payload: MemberCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemberRead:
    require_owner(db, workspace_id, user)
    added_user = db.scalar(select(User).where(User.email == normalize_email(payload.email)))
    if added_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    membership = WorkspaceMember(
        workspace_id=workspace_id, user_id=added_user.id, role=payload.role
    )
    db.add(membership)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="User is already a member") from error
    return MemberRead(
        user_id=added_user.id,
        email=added_user.email,
        display_name=added_user.display_name,
        role=membership.role,
    )


@router.patch("/{workspace_id}/members/{member_user_id}", response_model=MemberRead)
def update_member(
    workspace_id: int,
    member_user_id: int,
    payload: MemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemberRead:
    require_owner(db, workspace_id, user)
    membership = get_membership(db, workspace_id, member_user_id)
    ensure_owner_remains(db, workspace_id, membership, payload.role)
    membership.role = payload.role
    db.commit()
    return MemberRead(
        user_id=membership.user_id,
        email=membership.user.email,
        display_name=membership.user.display_name,
        role=membership.role,
    )


@router.delete("/{workspace_id}/members/{member_user_id}", status_code=204)
def remove_member(
    workspace_id: int,
    member_user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    require_owner(db, workspace_id, user)
    membership = get_membership(db, workspace_id, member_user_id)
    ensure_owner_remains(db, workspace_id, membership, None)
    assigned_task = db.scalar(
        select(TaskAssignee.task_id)
        .join(Task, Task.id == TaskAssignee.task_id)
        .where(
            Task.workspace_id == workspace_id,
            TaskAssignee.user_id == member_user_id,
        )
        .limit(1)
    )
    if assigned_task is not None:
        raise HTTPException(
            status_code=409,
            detail="Remove this member from assigned tasks before removing membership",
        )
    db.delete(membership)
    db.commit()
    return Response(status_code=204)


@router.get("/{workspace_id}/statuses", response_model=list[StatusRead])
def list_statuses(
    workspace_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TaskStatus]:
    get_membership(db, workspace_id, user.id)
    return list(
        db.scalars(
            select(TaskStatus)
            .where(TaskStatus.workspace_id == workspace_id)
            .order_by(TaskStatus.id)
        ).all()
    )


@router.post("/{workspace_id}/statuses", response_model=StatusRead, status_code=201)
def create_status(
    workspace_id: int,
    payload: StatusCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskStatus:
    require_editor(db, workspace_id, user)
    item = TaskStatus(workspace_id=workspace_id, **payload.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Status name already exists") from error
    db.refresh(item)
    return item


@router.patch("/{workspace_id}/statuses/{status_id}", response_model=StatusRead)
def update_status(
    workspace_id: int,
    status_id: int,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskStatus:
    require_editor(db, workspace_id, user)
    item = db.get(TaskStatus, status_id)
    if item is None or item.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Status not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Status name already exists") from error
    return item


@router.delete("/{workspace_id}/statuses/{status_id}", status_code=204)
def delete_status(
    workspace_id: int,
    status_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    require_editor(db, workspace_id, user)
    item = db.get(TaskStatus, status_id)
    if item is None or item.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Status not found")
    db.delete(item)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Status is in use") from error
    return Response(status_code=204)
