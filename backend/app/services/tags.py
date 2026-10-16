from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag, TagRelationship
from app.schemas import TagSummary


def tag_display_names(db: Session, user_id: int) -> dict[int, str]:
    tags = dict(db.execute(select(Tag.id, Tag.name).where(Tag.user_id == user_id)).all())
    parents: dict[int, set[int]] = defaultdict(set)
    if tags:
        for child_id, parent_id in db.execute(
            select(TagRelationship.child_tag_id, TagRelationship.parent_tag_id).where(
                TagRelationship.child_tag_id.in_(tags)
            )
        ):
            if parent_id in tags:
                parents[child_id].add(parent_id)

    def path_to(tag_id: int, seen: frozenset[int] = frozenset()) -> list[tuple[str, ...]]:
        if tag_id in seen or not parents[tag_id]:
            return [(tags[tag_id],)]
        return [
            (*path, tags[tag_id])
            for parent_id in parents[tag_id]
            for path in path_to(parent_id, seen | {tag_id})
        ]

    duplicates: dict[str, list[int]] = defaultdict(list)
    for tag_id, name in tags.items():
        duplicates[name.casefold()].append(tag_id)

    result = tags.copy()
    for tag_ids in duplicates.values():
        if len(tag_ids) < 2:
            continue
        for tag_id in tag_ids:
            if parents[tag_id]:
                contexts = [path for parent_id in parents[tag_id] for path in path_to(parent_id)]
                context = min(
                    contexts, key=lambda path: (len(path), tuple(part.casefold() for part in path))
                )
                result[tag_id] = f"{tags[tag_id]} ({' › '.join(context)})"
    while True:
        by_display: dict[str, list[int]] = defaultdict(list)
        for tag_id, display_name in result.items():
            by_display[display_name.casefold()].append(tag_id)
        collisions = [tag_ids for tag_ids in by_display.values() if len(tag_ids) > 1]
        if not collisions:
            break
        for tag_ids in collisions:
            for tag_id in tag_ids:
                result[tag_id] = f"{result[tag_id]} [#{tag_id}]"
    return result


def tag_summary(tag: Tag, display_names: dict[int, str]) -> TagSummary:
    return TagSummary(
        id=tag.id,
        name=tag.name,
        display_name=display_names[tag.id],
        color=tag.color,
        score_value=tag.score_value,
    )


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
    if child.user_id != parent.user_id:
        raise HTTPException(status_code=422, detail="Tags must belong to the same user")
    if child.id in ancestor_ids(db, [parent.id]):
        raise HTTPException(status_code=422, detail="Tag relationship would create a cycle")


def tags_by_ids(db: Session, tag_ids: set[int]) -> list[Tag]:
    if not tag_ids:
        return []
    return list(db.scalars(select(Tag).where(Tag.id.in_(tag_ids)).order_by(Tag.name, Tag.id)).all())
