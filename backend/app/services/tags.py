from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag, TagRelationship


def ancestor_ids(db: Session, tag_ids: list[int] | set[int]) -> set[int]:
    if not tag_ids:
        return set()
    ancestors = (
        select(TagRelationship.parent_tag_id.label("tag_id"))
        .where(TagRelationship.child_tag_id.in_(tag_ids))
        .cte(name="ancestors", recursive=True)
    )
    ancestors = ancestors.union(
        select(TagRelationship.parent_tag_id).join(
            ancestors, TagRelationship.child_tag_id == ancestors.c.tag_id
        )
    )
    return set(db.scalars(select(ancestors.c.tag_id)).all())


def descendant_ids(db: Session, tag_id: int) -> set[int]:
    descendants = (
        select(TagRelationship.child_tag_id.label("tag_id"))
        .where(TagRelationship.parent_tag_id == tag_id)
        .cte(name="descendants", recursive=True)
    )
    descendants = descendants.union(
        select(TagRelationship.child_tag_id).join(
            descendants, TagRelationship.parent_tag_id == descendants.c.tag_id
        )
    )
    return {tag_id, *db.scalars(select(descendants.c.tag_id)).all()}


def validate_relationship(db: Session, child: Tag, parent: Tag) -> None:
    if child.id == parent.id:
        raise HTTPException(status_code=422, detail="A tag cannot be its own parent")
    if child.workspace_id != parent.workspace_id:
        raise HTTPException(status_code=422, detail="Tags must belong to the same workspace")
    if child.id in ancestor_ids(db, [parent.id]):
        raise HTTPException(status_code=422, detail="Tag relationship would create a cycle")


def tags_by_ids(db: Session, tag_ids: set[int]) -> list[Tag]:
    if not tag_ids:
        return []
    return list(db.scalars(select(Tag).where(Tag.id.in_(tag_ids)).order_by(Tag.name)).all())
