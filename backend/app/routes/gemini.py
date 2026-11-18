from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.config import get_settings
from app.database import get_db
from app.gemini_schemas import (
    GeminiKeyUpdate,
    GeminiModelRead,
    GeminiModelUpdate,
    GeminiSettingsRead,
    TextToTaskDraft,
    TextToTaskRequest,
)
from app.i18n import error_detail, localized
from app.models import Tag, TagRelationship, Task, User
from app.services.credentials import CredentialError, decrypt_credential, encrypt_credential
from app.services.gemini import GeminiServiceError, generate_task_draft, list_gemini_models
from app.services.tags import ancestor_ids, tag_display_names

router = APIRouter(tags=["gemini"])


def integration_status(user: User) -> GeminiSettingsRead:
    configured = bool(user.gemini_api_key_encrypted)
    return GeminiSettingsRead(
        configured=configured,
        masked_key="••••••••••••" if configured else None,
        model=user.gemini_model or get_settings().gemini_model,
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
        raise HTTPException(status_code=503, detail=error_detail(error)) from error
    user.gemini_model = None
    db.commit()
    return integration_status(user)


@router.get("/api/integrations/gemini/models", response_model=list[GeminiModelRead])
def get_gemini_models(user: User = Depends(get_current_user)) -> list[GeminiModelRead]:
    if not user.gemini_api_key_encrypted:
        raise HTTPException(
            status_code=409, detail=localized("api.addAGeminiApiKeyBeforeChoosingAModel")
        )
    try:
        return list_gemini_models(decrypt_credential(user.gemini_api_key_encrypted))
    except CredentialError as error:
        raise HTTPException(status_code=503, detail=error_detail(error)) from error
    except GeminiServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error_detail(error)) from error


@router.put("/api/integrations/gemini/model", response_model=GeminiSettingsRead)
def save_gemini_model(
    payload: GeminiModelUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GeminiSettingsRead:
    available = get_gemini_models(user)
    if payload.model not in {item.id for item in available}:
        raise HTTPException(
            status_code=422, detail=localized("api.chooseATextModelAvailableForThisApiKey")
        )
    user.gemini_model = payload.model
    db.commit()
    return integration_status(user)


@router.delete("/api/integrations/gemini", response_model=GeminiSettingsRead)
def delete_gemini_key(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GeminiSettingsRead:
    user.gemini_api_key_encrypted = None
    user.gemini_model = None
    db.commit()
    return integration_status(user)


def _normalize_tag(value: str) -> str:
    return value.strip().removeprefix("#").strip().lower()


@router.post(
    "/api/task-drafts/from-text",
    response_model=TextToTaskDraft,
)
def text_to_task(
    payload: TextToTaskRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TextToTaskDraft:
    if not user.gemini_api_key_encrypted:
        raise HTTPException(
            status_code=409,
            detail=localized("api.addAGeminiApiKeyInSettingsBeforeUsing"),
        )
    tags = list(
        db.scalars(select(Tag).where(Tag.user_id == user.id).order_by(Tag.name, Tag.id)).all()
    )
    tasks = [
        task
        for task in db.scalars(
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.priority > 0,
                Task.finished_at.is_(None),
            )
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
        .unique()
        .all()
        if task.abandoned_by_task_id is None
    ]
    display_names = tag_display_names(db, user.id)
    tag_ids = {item.id for item in tags}
    parents_by_child: dict[int, list[str]] = {}
    if tag_ids:
        for child_id, parent_id in db.execute(
            select(TagRelationship.child_tag_id, TagRelationship.parent_tag_id).where(
                TagRelationship.child_tag_id.in_(tag_ids),
                TagRelationship.parent_tag_id.in_(tag_ids),
            )
        ):
            parents_by_child.setdefault(child_id, []).append(display_names[parent_id])
    context = {
        "today": date.today().isoformat(),
        "existing_tags": [display_names[item.id] for item in tags],
        "tag_parents": {
            display_names[item.id]: sorted(parents_by_child[item.id])
            for item in tags
            if item.id in parents_by_child
        },
        "existing_tasks": [{"id": item.id, "title": item.title} for item in tasks],
    }
    try:
        api_key = decrypt_credential(user.gemini_api_key_encrypted)
        model = user.gemini_model or get_settings().gemini_model
        generated = generate_task_draft(api_key, context, payload.text, model=model)
    except CredentialError as error:
        raise HTTPException(status_code=503, detail=error_detail(error)) from error
    except GeminiServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error_detail(error)) from error

    tags_by_name: dict[str, list[Tag]] = {}
    for tag in tags:
        tags_by_name.setdefault(tag.name.casefold(), []).append(tag)
    tags_by_display = {display_names[item.id].casefold(): item for item in tags}
    existing_tag_ids: list[int] = []
    new_tag_names: list[str] = []
    seen_names: set[str] = set()
    for suggested in generated.tag_names:
        name = _normalize_tag(suggested)
        if not name or name.casefold() in seen_names:
            continue
        seen_names.add(name.casefold())
        existing = tags_by_display.get(name.casefold())
        if existing is None and len(tags_by_name.get(name.casefold(), [])) == 1:
            existing = tags_by_name[name.casefold()][0]
        if existing:
            if existing.id not in existing_tag_ids:
                existing_tag_ids.append(existing.id)
        elif name.casefold() not in tags_by_name:
            new_tag_names.append(name[:120])

    ancestors = ancestor_ids(db, existing_tag_ids)
    existing_tag_ids = [tag_id for tag_id in existing_tag_ids if tag_id not in ancestors]
    valid_parent_ids = {item.id for item in tasks}
    parent_task_id = (
        generated.parent_task_id if generated.parent_task_id in valid_parent_ids else None
    )

    return TextToTaskDraft(
        title=generated.title.strip(),
        description=generated.description.strip() if generated.description else None,
        priority=generated.priority,
        due_date=generated.due_date,
        parent_task_id=parent_task_id,
        existing_tag_ids=existing_tag_ids,
        new_tag_names=new_tag_names,
        model=model,
    )
