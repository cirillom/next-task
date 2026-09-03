from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import Tag, TagRelationship, User
from app.schemas import TagCreate, TagRead, TagRelationshipCreate, TagSummary, TagUpdate
from app.services.tags import ancestor_ids, tags_by_ids, validate_relationship
from app.services.workspaces import get_membership, require_editor

router = APIRouter(prefix="/api/workspaces/{workspace_id}/tags", tags=["tags"])


def get_tag(db: Session, workspace_id: int, tag_id: int) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None or tag.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


def tag_read(db: Session, tag: Tag) -> TagRead:
    parent_ids = set(
        db.scalars(
            select(TagRelationship.parent_tag_id).where(TagRelationship.child_tag_id == tag.id)
        ).all()
    )
    child_ids = set(
        db.scalars(
            select(TagRelationship.child_tag_id).where(TagRelationship.parent_tag_id == tag.id)
        ).all()
    )
    return TagRead(
        id=tag.id,
        workspace_id=tag.workspace_id,
        name=tag.name,
        description=tag.description,
        color=tag.color,
        parents=[TagSummary.model_validate(item) for item in tags_by_ids(db, parent_ids)],
        children=[TagSummary.model_validate(item) for item in tags_by_ids(db, child_ids)],
        ancestors=[
            TagSummary.model_validate(item) for item in tags_by_ids(db, ancestor_ids(db, [tag.id]))
        ],
    )


@router.get("", response_model=list[TagRead])
def list_tags(
    workspace_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TagRead]:
    get_membership(db, workspace_id, user.id)
    tags = db.scalars(select(Tag).where(Tag.workspace_id == workspace_id).order_by(Tag.name)).all()
    return [tag_read(db, tag) for tag in tags]


@router.post("", response_model=TagRead, status_code=201)
def create_tag(
    workspace_id: int,
    payload: TagCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagRead:
    require_editor(db, workspace_id, user)
    tag = Tag(workspace_id=workspace_id, **payload.model_dump())
    db.add(tag)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tag name already exists") from error
    db.refresh(tag)
    return tag_read(db, tag)


@router.patch("/{tag_id}", response_model=TagRead)
def update_tag(
    workspace_id: int,
    tag_id: int,
    payload: TagUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagRead:
    require_editor(db, workspace_id, user)
    tag = get_tag(db, workspace_id, tag_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tag, key, value)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tag name already exists") from error
    return tag_read(db, tag)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(
    workspace_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    require_editor(db, workspace_id, user)
    db.delete(get_tag(db, workspace_id, tag_id))
    db.commit()
    return Response(status_code=204)


@router.post("/{tag_id}/parents", response_model=TagRead, status_code=201)
def add_parent(
    workspace_id: int,
    tag_id: int,
    payload: TagRelationshipCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagRead:
    require_editor(db, workspace_id, user)
    child = get_tag(db, workspace_id, tag_id)
    parent = get_tag(db, workspace_id, payload.parent_tag_id)
    validate_relationship(db, child, parent)
    db.add(TagRelationship(child_tag_id=child.id, parent_tag_id=parent.id))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Relationship already exists") from error
    return tag_read(db, child)


@router.delete("/{tag_id}/parents/{parent_tag_id}", response_model=TagRead)
def remove_parent(
    workspace_id: int,
    tag_id: int,
    parent_tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagRead:
    require_editor(db, workspace_id, user)
    child = get_tag(db, workspace_id, tag_id)
    relationship = db.get(TagRelationship, (tag_id, parent_tag_id))
    if relationship is None:
        raise HTTPException(status_code=404, detail="Relationship not found")
    db.delete(relationship)
    db.commit()
    return tag_read(db, child)
