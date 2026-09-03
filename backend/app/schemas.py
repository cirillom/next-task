from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import WorkspaceRole


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(ApiModel):
    message: str


class UserRead(ApiModel):
    id: int
    email: str
    display_name: str
    created_at: datetime


class LoginRequest(ApiModel):
    email: str
    password: str


class PasswordChange(ApiModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=1024)


class WorkspaceCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class WorkspaceUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    scoring_formula: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class WorkspaceRead(ApiModel):
    id: int
    name: str
    scoring_formula: str | None
    created_at: datetime
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
    score_value: float = 0

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class StatusUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    score_value: float | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


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
    blocked_at: datetime
    unblocked_at: datetime | None


class TaskSummary(ApiModel):
    id: int
    title: str
    finished_at: datetime | None


class TaskCreate(ApiModel):
    workspace_id: int
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    status_id: int
    priority: int = Field(default=1, ge=1)
    due_date: date | None = None
    last_worked_at: datetime | None = None
    parent_task_id: int | None = None
    assignee_ids: list[int] = Field(default_factory=list)
    tag_ids: list[int] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return value.strip()


class TaskUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status_id: int | None = None
    priority: int | None = Field(default=None, ge=1)
    due_date: date | None = None
    last_worked_at: datetime | None = None
    parent_task_id: int | None = None
    assignee_ids: list[int] | None = None
    tag_ids: list[int] | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


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
    last_worked_at: datetime | None
    finished_at: datetime | None
    parent_task_id: int | None
    created_at: datetime
    updated_at: datetime
    score: float
    assignees: list[UserRead]
    direct_tags: list[TagSummary]
    inherited_tags: list[TagSummary]
    current_block: BlockRead | None
    blocking_history: list[BlockRead]
    subtasks: list[TaskSummary]


class BlockCreate(ApiModel):
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        return value.strip()


class TagCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip().removeprefix("#").lower()


class TagUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return value.strip().removeprefix("#").lower() if value is not None else None


class TagRead(TagSummary):
    workspace_id: int
    description: str | None
    parents: list[TagSummary]
    children: list[TagSummary]
    ancestors: list[TagSummary]


class TagRelationshipCreate(ApiModel):
    parent_tag_id: int
