from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User, WorkspaceMember, WorkspaceRole


def get_membership(db: Session, workspace_id: int, user_id: int) -> WorkspaceMember:
    membership = db.get(WorkspaceMember, (user_id, workspace_id))
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return membership


def require_editor(db: Session, workspace_id: int, user: User) -> WorkspaceMember:
    membership = get_membership(db, workspace_id, user.id)
    if membership.role == WorkspaceRole.VIEWER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Read-only workspace")
    return membership


def require_owner(db: Session, workspace_id: int, user: User) -> WorkspaceMember:
    membership = get_membership(db, workspace_id, user.id)
    if membership.role != WorkspaceRole.OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    return membership


def ensure_owner_remains(
    db: Session, workspace_id: int, membership: WorkspaceMember, next_role: WorkspaceRole | None
) -> None:
    if membership.role != WorkspaceRole.OWNER or next_role == WorkspaceRole.OWNER:
        return
    owner_count = db.scalar(
        select(func.count())
        .select_from(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == WorkspaceRole.OWNER,
        )
    )
    if owner_count == 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A workspace must keep at least one owner",
        )
