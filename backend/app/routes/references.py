from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import Tag, TagRelationship, Task, User

router = APIRouter(prefix="/api/references", tags=["references"])


class ReferenceKey(BaseModel):
    kind: Literal["task", "tag"]
    id: int = Field(gt=0)


class ReferenceBatch(BaseModel):
    items: list[ReferenceKey] = Field(max_length=100)


class ReferenceResult(ReferenceKey):
    label: str | None
    paths: list[str] = Field(default_factory=list)


def tag_paths(db: Session, user_id: int, wanted: set[int]) -> dict[int, list[str]]:
    if not wanted:
        return {}
    names = dict(db.execute(select(Tag.id, Tag.name).where(Tag.user_id == user_id)).all())
    parents: dict[int, set[int]] = defaultdict(set)
    for child, parent in db.execute(
        select(TagRelationship.child_tag_id, TagRelationship.parent_tag_id).where(
            TagRelationship.child_tag_id.in_(names)
        )
    ):
        if parent in names:
            parents[child].add(parent)

    def paths(tag_id: int, seen: frozenset[int]) -> list[str]:
        # shortcut: cap deep or branching paths, raise limits for larger graphs.
        if tag_id in seen or len(seen) >= 128 or not parents[tag_id]:
            return [names[tag_id]]
        result = []
        for parent in sorted(parents[tag_id], key=lambda item: (names[item].casefold(), item)):
            for path in paths(parent, seen | {tag_id}):
                result.append(f"{path} › {names[tag_id]}")
                if len(result) == 50:
                    return result
        return result

    return {tag_id: paths(tag_id, frozenset()) for tag_id in wanted if tag_id in names}


@router.get("", response_model=list[ReferenceResult])
def search_references(
    query: str = Query(default="", max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReferenceResult]:
    query = query.strip()
    pattern = f"%{query}%"
    task_filter = Task.title.ilike(pattern)
    tag_filter = Tag.name.ilike(pattern)
    if query.isascii() and query.isdecimal() and len(query) <= 19 and int(query) <= 2**63 - 1:
        task_filter = or_(task_filter, Task.id == int(query))
        tag_filter = or_(tag_filter, Tag.id == int(query))
    tasks = db.execute(
        select(Task.id, Task.title)
        .where(Task.user_id == user.id, task_filter)
        .order_by(Task.title, Task.id)
        .limit(limit)
    ).all()
    tags = db.execute(
        select(Tag.id, Tag.name)
        .where(Tag.user_id == user.id, tag_filter)
        .order_by(Tag.name, Tag.id)
        .limit(max(0, limit - len(tasks)))
    ).all()
    paths = tag_paths(db, user.id, {item.id for item in tags})
    return [ReferenceResult(kind="task", id=item.id, label=item.title) for item in tasks] + [
        ReferenceResult(kind="tag", id=item.id, label=item.name, paths=paths[item.id])
        for item in tags
    ]


@router.post("/resolve", response_model=list[ReferenceResult])
def resolve_references(
    payload: ReferenceBatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReferenceResult]:
    keys = list(dict.fromkeys((item.kind, item.id) for item in payload.items))
    task_ids = {id for kind, id in keys if kind == "task"}
    tag_ids = {id for kind, id in keys if kind == "tag"}
    tasks = dict(
        db.execute(
            select(Task.id, Task.title).where(Task.user_id == user.id, Task.id.in_(task_ids))
        ).all()
    )
    tags = dict(
        db.execute(
            select(Tag.id, Tag.name).where(Tag.user_id == user.id, Tag.id.in_(tag_ids))
        ).all()
    )
    paths = tag_paths(db, user.id, set(tags))
    return [
        ReferenceResult(
            kind=kind,
            id=id,
            label=(tasks if kind == "task" else tags).get(id),
            paths=paths.get(id, []) if kind == "tag" else [],
        )
        for kind, id in keys
    ]
