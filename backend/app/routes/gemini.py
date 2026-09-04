from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.config import get_settings
from app.database import get_db
from app.gemini_schemas import (
    GeminiKeyUpdate,
    GeminiSettingsRead,
    TextToTaskDraft,
    TextToTaskRequest,
)
from app.models import Tag, TaskStatus, User, WorkspaceMember
from app.services.credentials import CredentialError, decrypt_credential, encrypt_credential
from app.services.gemini import GeminiServiceError, generate_task_draft
from app.services.workspaces import require_editor

router = APIRouter(tags=["gemini"])


def integration_status(user: User) -> GeminiSettingsRead:
    configured = bool(user.gemini_api_key_encrypted)
    return GeminiSettingsRead(
        configured=configured,
        masked_key="••••••••••••" if configured else None,
        model=get_settings().gemini_model,
    )


@router.get("/api/integrations/gemini", response_model=GeminiSettingsRead)
def get_gemini_settings(user: User = Depends(get_current_user)) -> GeminiSettingsRead:
    return integration_status(user)


@router.put("/api/integrations/gemini", response_model=GeminiSettingsRead)
def save_gemini_key(
    payload: GeminiKeyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GeminiSettingsRead:
    try:
        user.gemini_api_key_encrypted = encrypt_credential(payload.api_key)
    except CredentialError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    db.commit()
    return integration_status(user)


@router.delete("/api/integrations/gemini", response_model=GeminiSettingsRead)
def delete_gemini_key(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GeminiSettingsRead:
    user.gemini_api_key_encrypted = None
    db.commit()
    return integration_status(user)


def _normalize_tag(value: str) -> str:
    return value.strip().removeprefix("#").strip().lower()[:120]


@router.post(
    "/api/workspaces/{workspace_id}/task-drafts/from-text",
    response_model=TextToTaskDraft,
)
def text_to_task(
    workspace_id: int,
    payload: TextToTaskRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TextToTaskDraft:
    membership = require_editor(db, workspace_id, user)
    if not user.gemini_api_key_encrypted:
        raise HTTPException(
            status_code=409,
            detail="Add a Gemini API key in Settings before using text to task",
        )
    statuses = list(
        db.scalars(
            select(TaskStatus)
            .where(TaskStatus.workspace_id == workspace_id)
            .order_by(TaskStatus.id)
        ).all()
    )
    members = list(
        db.scalars(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.user_id)
        ).all()
    )
    tags = list(
        db.scalars(select(Tag).where(Tag.workspace_id == workspace_id).order_by(Tag.name)).all()
    )
    if not statuses:
        raise HTTPException(status_code=409, detail="The workspace needs at least one status")
    context = {
        "name": membership.workspace.name,
        "today": date.today().isoformat(),
        "statuses": [{"name": item.name} for item in statuses],
        "members": [
            {"name": item.user.display_name, "email": item.user.email} for item in members
        ],
        "existing_tags": [item.name for item in tags],
    }
    try:
        api_key = decrypt_credential(user.gemini_api_key_encrypted)
        generated = generate_task_draft(api_key, context, payload.text)
    except CredentialError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except GeminiServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    status_by_name = {item.name.casefold(): item for item in statuses}
    chosen_status = status_by_name.get(generated.status_name.casefold(), statuses[0])
    member_by_email = {item.user.email.casefold(): item for item in members}
    assignee_ids = list(
        dict.fromkeys(
            member_by_email[email.casefold()].user_id
            for email in generated.assignee_emails
            if email.casefold() in member_by_email
        )
    )
    tag_by_name = {item.name.casefold(): item for item in tags}
    existing_tag_ids: list[int] = []
    new_tag_names: list[str] = []
    seen_names: set[str] = set()
    for suggested in generated.tag_names:
        name = _normalize_tag(suggested)
        if not name or name.casefold() in seen_names:
            continue
        seen_names.add(name.casefold())
        existing = tag_by_name.get(name.casefold())
        if existing:
            existing_tag_ids.append(existing.id)
        else:
            new_tag_names.append(name)

    return TextToTaskDraft(
        title=generated.title.strip(),
        description=generated.description.strip() if generated.description else None,
        status_id=chosen_status.id,
        priority=generated.priority,
        due_date=generated.due_date,
        assignee_ids=assignee_ids,
        existing_tag_ids=existing_tag_ids,
        new_tag_names=new_tag_names,
        model=get_settings().gemini_model,
    )
