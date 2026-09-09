from datetime import UTC, date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.models import WorkspaceRole


def clean_required(value: str, tag: bool = False) -> str:
    cleaned = value.strip().removeprefix("#").lower() if tag else value.strip()
    if not cleaned:
        raise ValueError("Value cannot be blank")
    return cleaned


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


# SQLite returns naive datetimes; API timestamps always identify a UTC instant.
UtcDateTime = Annotated[datetime, AfterValidator(ensure_utc)]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(ApiModel):
    message: str


class UserRead(ApiModel):
    id: int
    email: str
    display_name: str
    created_at: UtcDateTime


class LoginRequest(ApiModel):
    email: str
    password: str


class SignUpRequest(ApiModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=10, max_length=1024)

    @field_validator("identifier")
    @classmethod
    def clean_identifier(cls, value: str) -> str:
        return clean_required(value).lower()


class PasswordChange(ApiModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=1024)


class McpSettingsRead(ApiModel):
    connector_url: str
    active_connections: int


class WorkspaceCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return clean_required(value)


class WorkspaceUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    scoring_formula: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return clean_required(value) if value is not None else None


class WorkspaceRead(ApiModel):
    id: int
    name: str
    scoring_formula: str | None
    created_at: UtcDateTime
    role: WorkspaceRole


class MemberCreate(ApiModel):
    email: str
    role: WorkspaceRole = WorkspaceRole.EDITOR


class MemberUpdate(ApiModel):
    role: WorkspaceRole


class MemberRead(ApiModel):
    user_id: int
    email: str
    display_name: str
    role: WorkspaceRole


class StatusCreate(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    score_value: float = Field(default=0, allow_inf_nan=False)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return clean_required(value)


class StatusUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    score_value: float | None = Field(default=None, allow_inf_nan=False)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return clean_required(value) if value is not None else None


class StatusRead(ApiModel):
    id: int
    workspace_id: int
    name: str
    score_value: float


class TagSummary(ApiModel):
    id: int
    name: str
    color: str | None


class BlockRead(ApiModel):
    id: int
    reason: str
    blocked_at: UtcDateTime
    unblocked_at: UtcDateTime | None


class TaskSummary(ApiModel):
    id: int
    title: str
    finished_at: UtcDateTime | None
    unfinished_descendant_count: int = 0


class TaskCreate(ApiModel):
    workspace_id: int
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    status_id: int
    priority: int = Field(default=1, ge=1)
    due_date: date | None = None
    last_worked_at: UtcDateTime | None = None
    parent_task_id: int | None = None
    assignee_ids: list[int] = Field(default_factory=list)
    tag_ids: list[int] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return clean_required(value)


class TaskUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status_id: int | None = None
    priority: int | None = Field(default=None, ge=1)
    due_date: date | None = None
    last_worked_at: UtcDateTime | None = None
    parent_task_id: int | None = None
    assignee_ids: list[int] | None = None
    tag_ids: list[int] | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return clean_required(value) if value is not None else None


class TaskRead(ApiModel):
    id: int
    created_by_user_id: int
    creator: UserRead
    workspace_id: int
    title: str
    description: str | None
    status: StatusRead
    priority: int
    due_date: date | None
    last_worked_at: UtcDateTime | None
    finished_at: UtcDateTime | None
    parent_task_id: int | None
    parent_task: TaskSummary | None
    unfinished_descendant_count: int
    created_at: UtcDateTime
    updated_at: UtcDateTime
    score: float
    ranking_score: float
    ranking_source_task_id: int | None
    ranking_source_score: float | None
    assignees: list[UserRead]
    direct_tags: list[TagSummary]
    inherited_tags: list[TagSummary]
    current_block: BlockRead | None
    blocking_history: list[BlockRead]
    subtasks: list[TaskSummary]


class BlockCreate(ApiModel):
    reason: str = Field(min_length=1, max_length=4000)
    unblocked_at: UtcDateTime | None = None

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        return clean_required(value)


class BlockReblock(ApiModel):
    unblocked_at: UtcDateTime | None = None


class TagCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return clean_required(value, tag=True)


class TagUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return clean_required(value, tag=True) if value is not None else None


class TagRead(TagSummary):
    workspace_id: int
    description: str | None
    parents: list[TagSummary]
    children: list[TagSummary]
    ancestors: list[TagSummary]


class TagRelationshipCreate(ApiModel):
    parent_tag_id: int
