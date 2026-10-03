from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import Tag, TagRelationship, TaskTag, User
from app.schemas import (
    TagCreate,
    TagMergeCreate,
    TagMergePreview,
    TagRead,
    TagRelationshipCreate,
    TagSummary,
    TagUpdate,
)
from app.services.tags import ancestor_ids, tags_by_ids, validate_relationship
from app.services.workspaces import get_membership, require_editor

router = APIRouter(prefix="/api/workspaces/{workspace_id}/tags", tags=["tags"])


def get_tag(db: Session, workspace_id: int, tag_id: int) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None or tag.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


def tag_name_exists(
    db: Session, workspace_id: int, name: str, exclude_id: int | None = None
) -> bool:
    query = select(Tag.id).where(
        Tag.workspace_id == workspace_id, func.lower(Tag.name) == name.lower()
    )
    if exclude_id is not None:
        query = query.where(Tag.id != exclude_id)
    return db.scalar(query) is not None


def merge_plan(
    db: Session,
    source: Tag,
    destination: Tag,
) -> tuple[TagMergePreview, set[int], set[tuple[int, int]]]:
    if source.id == destination.id:
        raise HTTPException(status_code=422, detail="A tag cannot be merged into itself")

    workspace_tag_ids = set(
        db.scalars(select(Tag.id).where(Tag.workspace_id == source.workspace_id)).all()
    )
    relationships = {
        (child_id, parent_id)
        for child_id, parent_id in db.execute(
            select(TagRelationship.child_tag_id, TagRelationship.parent_tag_id).where(
                TagRelationship.child_tag_id.in_(workspace_tag_ids)
            )
        ).all()
        if parent_id in workspace_tag_ids
    }

    source_parent_ids = {
        parent_id for child_id, parent_id in relationships if child_id == source.id
    }
    source_child_ids = {
        child_id for child_id, parent_id in relationships if parent_id == source.id
    }
    base_relationships = {
        relationship
        for relationship in relationships
        if source.id not in relationship
    }
    replacement_relationships = {
        (destination.id, parent_id)
        for parent_id in source_parent_ids
        if parent_id != destination.id
    } | {
        (child_id, destination.id)
        for child_id in source_child_ids
        if child_id != destination.id
    }
    resulting_relationships = base_relationships | replacement_relationships

    parents_by_child: dict[int, set[int]] = {}
    for child_id, parent_id in resulting_relationships:
        parents_by_child.setdefault(child_id, set()).add(parent_id)

    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(tag_id: int) -> None:
        if tag_id in visiting:
            raise HTTPException(
                status_code=422,
                detail="Merge would create a tag hierarchy cycle",
            )
        if tag_id in visited:
            return
        visiting.add(tag_id)
        for parent_id in parents_by_child.get(tag_id, set()):
            visit(parent_id)
        visiting.remove(tag_id)
        visited.add(tag_id)

    for tag_id in workspace_tag_ids - {source.id}:
        visit(tag_id)

    source_task_ids = set(
        db.scalars(select(TaskTag.task_id).where(TaskTag.tag_id == source.id)).all()
    )
    destination_task_ids = set(
        db.scalars(select(TaskTag.task_id).where(TaskTag.tag_id == destination.id)).all()
    )

    preview = TagMergePreview(
        source_tag_id=source.id,
        destination_tag_id=destination.id,
        task_assignments=len(source_task_ids),
        parent_relationships=len(source_parent_ids),
        child_relationships=len(source_child_ids),
    )
    return (
        preview,
        source_task_ids - destination_task_ids,
        replacement_relationships - base_relationships,
    )


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
        score_value=tag.score_value,
        direct_task_count=len(tag.tasks),
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
    parent = (
        get_tag(db, workspace_id, payload.parent_tag_id)
        if payload.parent_tag_id is not None
        else None
    )
    if tag_name_exists(db, workspace_id, payload.name):
        raise HTTPException(status_code=409, detail="Tag name already exists")
    tag = Tag(
        workspace_id=workspace_id,
        **payload.model_dump(exclude={"parent_tag_id"}),
    )
    db.add(tag)
    try:
        db.flush()
        if parent is not None:
            validate_relationship(db, tag, parent)
            db.add(TagRelationship(child_tag_id=tag.id, parent_tag_id=parent.id))
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
    if payload.name is not None and tag_name_exists(db, workspace_id, payload.name, tag_id):
        raise HTTPException(status_code=409, detail="Tag name already exists")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tag, key, value)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tag name already exists") from error
    return tag_read(db, tag)


@router.get("/{tag_id}/merge-preview", response_model=TagMergePreview)
def preview_merge(
    workspace_id: int,
    tag_id: int,
    destination_tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagMergePreview:
    require_editor(db, workspace_id, user)
    source = get_tag(db, workspace_id, tag_id)
    destination = get_tag(db, workspace_id, destination_tag_id)
    preview, _, _ = merge_plan(db, source, destination)
    return preview


@router.post("/{tag_id}/merge", response_model=TagRead)
def merge_tag(
    workspace_id: int,
    tag_id: int,
    payload: TagMergeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagRead:
    require_editor(db, workspace_id, user)
    source = get_tag(db, workspace_id, tag_id)
    destination = get_tag(db, workspace_id, payload.destination_tag_id)
    _, task_ids_to_add, relationships_to_add = merge_plan(db, source, destination)

    try:
        for task_id in task_ids_to_add:
            db.add(TaskTag(task_id=task_id, tag_id=destination.id))

        db.execute(delete(TaskTag).where(TaskTag.tag_id == source.id))
        db.execute(
            delete(TagRelationship).where(
                or_(
                    TagRelationship.child_tag_id == source.id,
                    TagRelationship.parent_tag_id == source.id,
                )
            )
        )
        for child_id, parent_id in relationships_to_add:
            db.add(TagRelationship(child_tag_id=child_id, parent_tag_id=parent_id))

        db.delete(source)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tag merge could not be completed") from error

    db.refresh(destination)
    return tag_read(db, destination)


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
