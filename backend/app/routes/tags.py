from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, or_, select
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
    TagUpdate,
)
from app.services.tags import (
    ancestor_ids,
    tag_display_names,
    tag_summary,
    tags_by_ids,
    validate_relationship,
)

router = APIRouter(prefix="/api/tags", tags=["tags"])


def lock_tag_writes(db: Session) -> None:
    # Scope names live across tags and relationship rows, so serialize the check and write.
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def get_tag(db: Session, user_id: int, tag_id: int) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None or tag.user_id != user_id:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


def tag_name_conflicts(
    db: Session,
    user_id: int,
    name: str,
    parent_ids: set[int],
    exclude_ids: set[int] | None = None,
) -> bool:
    scope = parent_ids or {None}
    excluded = exclude_ids or set()
    for tag_id, existing_name in db.execute(
        select(Tag.id, Tag.name).where(Tag.user_id == user_id)
    ):
        if tag_id in excluded or existing_name.casefold() != name.casefold():
            continue
        existing_parents = set(
            db.scalars(
                select(TagRelationship.parent_tag_id).where(
                    TagRelationship.child_tag_id == tag_id
                )
            ).all()
        )
        if scope.intersection(existing_parents or {None}):
            return True
    return False


def merge_plan(
    db: Session,
    source: Tag,
    destination: Tag,
) -> tuple[TagMergePreview, set[int], set[tuple[int, int]]]:
    if source.id == destination.id:
        raise HTTPException(status_code=422, detail="A tag cannot be merged into itself")

    user_tag_ids = set(db.scalars(select(Tag.id).where(Tag.user_id == source.user_id)).all())
    relationships = {
        (child_id, parent_id)
        for child_id, parent_id in db.execute(
            select(TagRelationship.child_tag_id, TagRelationship.parent_tag_id).where(
                TagRelationship.child_tag_id.in_(user_tag_ids)
            )
        ).all()
        if parent_id in user_tag_ids
    }

    source_parent_ids = {
        parent_id for child_id, parent_id in relationships if child_id == source.id
    }
    source_child_ids = {child_id for child_id, parent_id in relationships if parent_id == source.id}
    base_relationships = {
        relationship for relationship in relationships if source.id not in relationship
    }
    replacement_relationships = {
        (destination.id, parent_id)
        for parent_id in source_parent_ids
        if parent_id != destination.id
    } | {(child_id, destination.id) for child_id in source_child_ids if child_id != destination.id}
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

    for tag_id in user_tag_ids - {source.id}:
        visit(tag_id)

    names = dict(
        db.execute(select(Tag.id, Tag.name).where(Tag.user_id == source.user_id)).all()
    )
    occupied: set[tuple[int | None, str]] = set()
    for tag_id in user_tag_ids - {source.id}:
        scopes = parents_by_child.get(tag_id) or {None}
        for parent_id in scopes:
            key = (parent_id, names[tag_id].casefold())
            if key in occupied:
                raise HTTPException(
                    status_code=422, detail="Merge would duplicate a sibling tag name"
                )
            occupied.add(key)

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


def tag_read(db: Session, tag: Tag, display_names: dict[int, str] | None = None) -> TagRead:
    names = display_names if display_names is not None else tag_display_names(db, tag.user_id)
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
        name=tag.name,
        display_name=names[tag.id],
        description=tag.description,
        color=tag.color,
        score_value=tag.score_value,
        direct_task_count=len(tag.tasks),
        parents=[tag_summary(item, names) for item in tags_by_ids(db, parent_ids)],
        children=[tag_summary(item, names) for item in tags_by_ids(db, child_ids)],
        ancestors=[
            tag_summary(item, names) for item in tags_by_ids(db, ancestor_ids(db, [tag.id]))
        ],
    )


@router.get("", response_model=list[TagRead])
def list_tags(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TagRead]:
    tags = db.scalars(select(Tag).where(Tag.user_id == user.id).order_by(Tag.name, Tag.id)).all()
    names = tag_display_names(db, user.id)
    return [tag_read(db, tag, names) for tag in tags]


@router.post("", response_model=TagRead, status_code=201)
def create_tag(
    payload: TagCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagRead:
    lock_tag_writes(db)
    parent = (
        get_tag(db, user.id, payload.parent_tag_id) if payload.parent_tag_id is not None else None
    )
    if tag_name_conflicts(db, user.id, payload.name, {parent.id} if parent else set()):
        raise HTTPException(status_code=409, detail="Tag name already exists under this parent")
    tag = Tag(
        user_id=user.id,
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
        raise HTTPException(status_code=409, detail="Tag could not be created") from error
    db.refresh(tag)
    return tag_read(db, tag)


@router.patch("/{tag_id}", response_model=TagRead)
def update_tag(
    tag_id: int,
    payload: TagUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagRead:
    lock_tag_writes(db)
    tag = get_tag(db, user.id, tag_id)
    parent_ids = set(
        db.scalars(
            select(TagRelationship.parent_tag_id).where(TagRelationship.child_tag_id == tag_id)
        ).all()
    )
    if payload.name is not None and tag_name_conflicts(
        db, user.id, payload.name, parent_ids, {tag_id}
    ):
        raise HTTPException(status_code=409, detail="Tag name already exists under this parent")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tag, key, value)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tag could not be updated") from error
    return tag_read(db, tag)


@router.get("/{tag_id}/merge-preview", response_model=TagMergePreview)
def preview_merge(
    tag_id: int,
    destination_tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagMergePreview:
    source = get_tag(db, user.id, tag_id)
    destination = get_tag(db, user.id, destination_tag_id)
    preview, _, _ = merge_plan(db, source, destination)
    return preview


@router.post("/{tag_id}/merge", response_model=TagRead)
def merge_tag(
    tag_id: int,
    payload: TagMergeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagRead:
    lock_tag_writes(db)
    source = get_tag(db, user.id, tag_id)
    destination = get_tag(db, user.id, payload.destination_tag_id)
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
    tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    lock_tag_writes(db)
    tag = get_tag(db, user.id, tag_id)
    child_ids = set(
        db.scalars(
            select(TagRelationship.child_tag_id).where(TagRelationship.parent_tag_id == tag_id)
        ).all()
    )
    for child_id in child_ids:
        other_parent = db.scalar(
            select(TagRelationship.parent_tag_id).where(
                TagRelationship.child_tag_id == child_id,
                TagRelationship.parent_tag_id != tag_id,
            )
        )
        child = db.get(Tag, child_id)
        if other_parent is None and child is not None and tag_name_conflicts(
            db, user.id, child.name, set(), {tag_id, child_id}
        ):
            raise HTTPException(
                status_code=409,
                detail="Deleting this tag would duplicate a root tag name",
            )
    db.delete(tag)
    db.commit()
    return Response(status_code=204)


@router.post("/{tag_id}/parents", response_model=TagRead, status_code=201)
def add_parent(
    tag_id: int,
    payload: TagRelationshipCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagRead:
    lock_tag_writes(db)
    child = get_tag(db, user.id, tag_id)
    parent = get_tag(db, user.id, payload.parent_tag_id)
    validate_relationship(db, child, parent)
    if tag_name_conflicts(db, user.id, child.name, {parent.id}, {child.id}):
        raise HTTPException(status_code=409, detail="Tag name already exists under this parent")
    db.add(TagRelationship(child_tag_id=child.id, parent_tag_id=parent.id))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Relationship already exists") from error
    return tag_read(db, child)


@router.delete("/{tag_id}/parents/{parent_tag_id}", response_model=TagRead)
def remove_parent(
    tag_id: int,
    parent_tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagRead:
    lock_tag_writes(db)
    child = get_tag(db, user.id, tag_id)
    relationship = db.get(TagRelationship, (tag_id, parent_tag_id))
    if relationship is None:
        raise HTTPException(status_code=404, detail="Relationship not found")
    other_parent = db.scalar(
        select(TagRelationship.parent_tag_id).where(
            TagRelationship.child_tag_id == tag_id,
            TagRelationship.parent_tag_id != parent_tag_id,
        )
    )
    if other_parent is None and tag_name_conflicts(db, user.id, child.name, set(), {tag_id}):
        raise HTTPException(
            status_code=409,
            detail="Removing this parent would duplicate a root tag name",
        )
    db.delete(relationship)
    db.commit()
    return tag_read(db, child)
