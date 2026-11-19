"""Shared implementation of the MCP task listing; transport supplies the user."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models import User
from app.routes.tasks import list_tasks_for_user
from app.services.tasks import validate_tags


class TaskListInput(BaseModel):
    finished: bool | None = False
    abandoned: Literal["exclude", "only", "include"] = "exclude"
    search: str | None = Field(default=None, max_length=300)
    blocked: bool | None = None
    actionable: bool = False
    include_tag_ids: list[Annotated[int, Field(gt=0)]] = Field(default_factory=list, max_length=100)
    exclude_tag_ids: list[Annotated[int, Field(gt=0)]] = Field(default_factory=list, max_length=100)
    tag_match: Literal["all", "any"] = "all"
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)


class TaskListOutput(BaseModel):
    items: list[dict]
    next_offset: int | None


def list_tasks(db: Session, user: User, params: TaskListInput) -> dict:
    validate_tags(db, user.id, params.include_tag_ids + params.exclude_tag_ids)
    tasks = list_tasks_for_user(
        db,
        user,
        finished=params.finished,
        abandoned=params.abandoned,
        include_tag_id=params.include_tag_ids,
        exclude_tag_id=params.exclude_tag_ids,
        tag_match=params.tag_match,
        blocked=params.blocked,
        actionable=params.actionable,
        search=params.search,
    )
    fields = {
        "id",
        "title",
        "priority",
        "due_date",
        "finished_at",
        "abandoned_at",
        "abandoned_by_task_id",
        "parent_task_id",
        "unfinished_descendant_count",
        "score",
        "ranking_score",
        "ranking_source_task_id",
        "ranking_source_score",
        "scoring_warning",
        "scoring_warning_code",
        "scoring_warning_params",
        "direct_tags",
        "inherited_tags",
        "current_block",
        "active_blocks",
    }
    end = params.offset + params.limit
    return {
        "items": [
            task.model_dump(mode="json", include=fields) for task in tasks[params.offset : end]
        ],
        "next_offset": end if end < len(tasks) else None,
    }
