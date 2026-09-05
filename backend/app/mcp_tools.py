from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Any

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Tag, TaskStatus, User, WorkspaceMember
from app.routes.tasks import (
    block_is_active,
)
from app.routes.tasks import (
    block_task as api_block_task,
)
from app.routes.tasks import (
    create_task as api_create_task,
)
from app.routes.tasks import (
    finish_task as api_finish_task,
)
from app.routes.tasks import (
    get_task as api_get_task,
)
from app.routes.tasks import (
    list_tasks as api_list_tasks,
)
from app.routes.tasks import (
    reopen_task as api_reopen_task,
)
from app.routes.tasks import (
    task_read,
)
from app.routes.tasks import (
    unblock_task as api_unblock_task,
)
from app.routes.tasks import (
    update_task as api_update_task,
)
from app.schemas import BlockCreate, TaskCreate, TaskUpdate
from app.services.tasks import get_task_for_user
from app.services.workspaces import get_membership, require_editor

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
IDEMPOTENT_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


def _current_user(db: Session) -> User:
    access_token = get_access_token()
    if access_token is None or access_token.subject is None:
        raise ToolError("Your Next Task connection is not authenticated")
    try:
        user_id = int(access_token.subject)
    except ValueError as error:
        raise ToolError("Your Next Task connection is invalid") from error
    user = db.get(User, user_id)
    if user is None:
        raise ToolError("Your Next Task account no longer exists")
    return user


@contextmanager
def _domain_errors(db: Session):
    try:
        yield
    except ToolError:
        raise
    except HTTPException as error:
        db.rollback()
        detail = error.detail if isinstance(error.detail, str) else "Next Task rejected the request"
        raise ToolError(detail) from error
    except IntegrityError as error:
        db.rollback()
        raise ToolError("The requested change conflicts with existing Next Task data") from error


def _json(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _status(db: Session, workspace_id: int, status_name: str | None) -> TaskStatus:
    query = select(TaskStatus).where(TaskStatus.workspace_id == workspace_id)
    if status_name:
        item = db.scalar(query.where(func.lower(TaskStatus.name) == status_name.strip().lower()))
        if item is None:
            raise ToolError(f"Status '{status_name}' does not exist in this workspace")
        return item
    item = db.scalar(query.where(func.lower(TaskStatus.name) == "todo"))
    item = item or db.scalar(query.order_by(TaskStatus.id))
    if item is None:
        raise ToolError("This workspace has no task statuses")
    return item


def _tag_names(db: Session, workspace_id: int, names: list[str], create_missing: bool) -> list[int]:
    cleaned = list(
        dict.fromkeys(
            name.strip().removeprefix("#").strip().lower()
            for name in names
            if name.strip().removeprefix("#").strip()
        )
    )
    if any(len(name) > 120 for name in cleaned):
        raise ToolError("Tag names must be 120 characters or fewer")
    existing = (
        list(
            db.scalars(
                select(Tag).where(
                    Tag.workspace_id == workspace_id,
                    func.lower(Tag.name).in_(cleaned),
                )
            ).all()
        )
        if cleaned
        else []
    )
    by_name = {tag.name.casefold(): tag for tag in existing}
    missing = [name for name in cleaned if name.casefold() not in by_name]
    if missing and not create_missing:
        raise ToolError(f"Unknown tags: {', '.join(missing)}")
    for name in missing:
        tag = Tag(workspace_id=workspace_id, name=name)
        db.add(tag)
        db.flush()
        by_name[name.casefold()] = tag
    return [by_name[name.casefold()].id for name in cleaned]


def _assignee_emails(db: Session, workspace_id: int, emails: list[str]) -> list[int]:
    memberships = list(
        db.scalars(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        ).all()
    )
    by_email = {membership.user.email.casefold(): membership.user_id for membership in memberships}
    normalized = list(dict.fromkeys(email.strip().casefold() for email in emails if email.strip()))
    missing = [email for email in normalized if email not in by_email]
    if missing:
        raise ToolError(f"These assignees are not workspace members: {', '.join(missing)}")
    return [by_email[email] for email in normalized]


def install_tools(server: MCPServer[Any]) -> None:
    @server.tool(annotations=READ_ONLY, structured_output=True)
    def list_workspaces() -> list[dict[str, Any]]:
        """List workspaces available to the connected Next Task user.

        Call this before choosing a workspace by name.
        """
        with SessionLocal() as db, _domain_errors(db):
            user = _current_user(db)
            memberships = list(
                db.scalars(
                    select(WorkspaceMember)
                    .where(WorkspaceMember.user_id == user.id)
                    .order_by(WorkspaceMember.workspace_id)
                ).all()
            )
            return [
                {
                    "id": item.workspace_id,
                    "name": item.workspace.name,
                    "role": item.role.value,
                }
                for item in memberships
            ]

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_workspace_context(workspace_id: int) -> dict[str, Any]:
        """Get valid statuses, tags, and assignees for a workspace.

        Call this before creating or editing a task to reuse its existing vocabulary.
        """
        with SessionLocal() as db, _domain_errors(db):
            user = _current_user(db)
            membership = get_membership(db, workspace_id, user.id)
            statuses = list(
                db.scalars(
                    select(TaskStatus)
                    .where(TaskStatus.workspace_id == workspace_id)
                    .order_by(TaskStatus.id)
                ).all()
            )
            tags = list(
                db.scalars(
                    select(Tag).where(Tag.workspace_id == workspace_id).order_by(Tag.name)
                ).all()
            )
            members = list(
                db.scalars(
                    select(WorkspaceMember)
                    .where(WorkspaceMember.workspace_id == workspace_id)
                    .order_by(WorkspaceMember.user_id)
                ).all()
            )
            return {
                "id": workspace_id,
                "name": membership.workspace.name,
                "role": membership.role.value,
                "statuses": [
                    {"id": item.id, "name": item.name, "score_value": item.score_value}
                    for item in statuses
                ],
                "tags": [{"id": item.id, "name": item.name, "color": item.color} for item in tags],
                "members": [
                    {
                        "id": item.user_id,
                        "name": item.user.display_name,
                        "email": item.user.email,
                        "role": item.role.value,
                    }
                    for item in members
                ],
            }

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def list_tasks(
        workspace_id: int,
        finished: bool = False,
        status_name: str | None = None,
        tag_name: str | None = None,
        blocked: bool | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List score-ranked tasks in a workspace.

        Optionally filter by status, tag, blocked state, or search text. Returns at most 100.
        """
        with SessionLocal() as db, _domain_errors(db):
            user = _current_user(db)
            get_membership(db, workspace_id, user.id)
            status_id = _status(db, workspace_id, status_name).id if status_name else None
            tag_id = None
            if tag_name:
                tag = db.scalar(
                    select(Tag).where(
                        Tag.workspace_id == workspace_id,
                        func.lower(Tag.name) == tag_name.strip().removeprefix("#").lower(),
                    )
                )
                if tag is None:
                    raise ToolError(f"Tag '{tag_name}' does not exist in this workspace")
                tag_id = tag.id
            tasks = api_list_tasks(
                workspace_id=workspace_id,
                finished=finished,
                status_id=status_id,
                tag_id=tag_id,
                assignee_id=None,
                blocked=blocked,
                search=search,
                db=db,
                user=user,
            )
            return [_json(task) for task in tasks[: max(1, min(limit, 100))]]

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_task(task_id: int) -> dict[str, Any]:
        """Get one task with its status, score, description, assignees, tags, subtasks,
        and blocking history.
        """
        with SessionLocal() as db, _domain_errors(db):
            user = _current_user(db)
            return _json(api_get_task(task_id=task_id, db=db, user=user))

    @server.tool(annotations=WRITE, structured_output=True)
    def create_task(
        workspace_id: int,
        title: str,
        description: str | None = None,
        status_name: str | None = None,
        priority: int = 1,
        due_date: date | None = None,
        tag_names: list[str] | None = None,
        assignee_emails: list[str] | None = None,
        parent_task_id: int | None = None,
        create_missing_tags: bool = True,
    ) -> dict[str, Any]:
        """Create a task after the user has confirmed its details.

        Prefer existing tags. Concise new tags may be created when create_missing_tags is true.
        """
        with SessionLocal() as db, _domain_errors(db):
            user = _current_user(db)
            require_editor(db, workspace_id, user)
            status = _status(db, workspace_id, status_name)
            tag_ids = _tag_names(db, workspace_id, tag_names or [], create_missing_tags)
            assignee_ids = _assignee_emails(db, workspace_id, assignee_emails or [])
            payload = TaskCreate(
                workspace_id=workspace_id,
                title=title,
                description=description,
                status_id=status.id,
                priority=priority,
                due_date=due_date,
                parent_task_id=parent_task_id,
                tag_ids=tag_ids,
                assignee_ids=assignee_ids,
            )
            return _json(api_create_task(payload=payload, db=db, user=user))

    @server.tool(annotations=WRITE, structured_output=True)
    def update_task(
        task_id: int,
        title: str | None = None,
        description: str | None = None,
        status_name: str | None = None,
        priority: int | None = None,
        due_date: date | None = None,
        tag_names: list[str] | None = None,
        assignee_emails: list[str] | None = None,
        parent_task_id: int | None = None,
        create_missing_tags: bool = True,
        clear_description: bool = False,
        clear_due_date: bool = False,
        clear_parent: bool = False,
    ) -> dict[str, Any]:
        """Update selected fields after the user has confirmed the changes.

        Omitted fields stay unchanged. Use clear flags to remove optional values.
        """
        with SessionLocal() as db, _domain_errors(db):
            user = _current_user(db)
            task = get_task_for_user(db, task_id, user)
            values: dict[str, Any] = {}
            if title is not None:
                values["title"] = title
            if description is not None or clear_description:
                values["description"] = None if clear_description else description
            if status_name is not None:
                values["status_id"] = _status(db, task.workspace_id, status_name).id
            if priority is not None:
                values["priority"] = priority
            if due_date is not None or clear_due_date:
                values["due_date"] = None if clear_due_date else due_date
            if tag_names is not None:
                values["tag_ids"] = _tag_names(
                    db, task.workspace_id, tag_names, create_missing_tags
                )
            if assignee_emails is not None:
                values["assignee_ids"] = _assignee_emails(db, task.workspace_id, assignee_emails)
            if parent_task_id is not None or clear_parent:
                values["parent_task_id"] = None if clear_parent else parent_task_id
            if not values:
                raise ToolError("No task changes were provided")
            payload = TaskUpdate.model_validate(values)
            return _json(api_update_task(task_id=task_id, payload=payload, db=db, user=user))

    @server.tool(annotations=IDEMPOTENT_WRITE, structured_output=True)
    def set_task_finished(task_id: int, finished: bool) -> dict[str, Any]:
        """Mark a task finished or reopen it. This does not change its workflow status."""
        with SessionLocal() as db, _domain_errors(db):
            user = _current_user(db)
            if finished:
                result = api_finish_task(task_id=task_id, db=db, user=user)
            else:
                result = api_reopen_task(task_id=task_id, db=db, user=user)
            return _json(result)

    @server.tool(annotations=IDEMPOTENT_WRITE, structured_output=True)
    def set_task_blocked(
        task_id: int,
        blocked: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Block a task with a reason or unblock it. A reason is required when blocking."""
        with SessionLocal() as db, _domain_errors(db):
            user = _current_user(db)
            task = get_task_for_user(db, task_id, user)
            is_blocked = any(block_is_active(block) for block in task.blocks)
            if blocked == is_blocked:
                return _json(task_read(db, task))
            if blocked:
                if not reason or not reason.strip():
                    raise ToolError("A reason is required to block a task")
                result = api_block_task(
                    task_id=task_id,
                    payload=BlockCreate(reason=reason),
                    db=db,
                    user=user,
                )
            else:
                result = api_unblock_task(task_id=task_id, db=db, user=user)
            return _json(result)
