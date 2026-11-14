from datetime import UTC, date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.i18n import Language, LocalizedText, localized, parameters
from app.services.mail import normalize_email_address


def clean_required(value: str, tag: bool = False) -> str:
    cleaned = value.strip().removeprefix("#") if tag else value.strip()
    if not cleaned:
        raise ValueError(localized("api.valueCannotBeBlank"))
    return cleaned


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


# SQLite returns naive datetimes; API timestamps always identify a UTC instant.
UtcDateTime = Annotated[datetime, AfterValidator(ensure_utc)]
EmailAddress = Annotated[str, Field(max_length=320), AfterValidator(normalize_email_address)]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(ApiModel):
    message: str
    code: str | None = None
    params: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def include_translation(cls, value: dict) -> dict:
        text = value.get("message")
        if isinstance(text, LocalizedText):
            value = {**value, "code": text.key, "params": parameters(text.values)}
        return value


class UserRead(ApiModel):
    id: int
    email: str
    display_name: str
    created_at: UtcDateTime
    language: Language


class LanguageUpdate(ApiModel):
    language: Language


class LoginRequest(ApiModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class PasswordChange(ApiModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=1024)


class EmailRequest(ApiModel):
    email: EmailAddress
    current_password: str = Field(max_length=1024)


class EmailStatus(ApiModel):
    verified: bool
    pending_email: str | None


class TokenRequest(ApiModel):
    token: str = Field(min_length=32, max_length=256)


class InvitationAccept(TokenRequest):
    language: Language | None = None
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=10, max_length=1024)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        return clean_required(value)


class PasswordResetRequest(ApiModel):
    email: str = Field(min_length=1, max_length=320)


class PasswordResetConfirm(TokenRequest):
    new_password: str = Field(min_length=10, max_length=1024)


class ScoringSettings(ApiModel):
    scoring_formula: str = Field(max_length=4000)


class TagSummary(ApiModel):
    id: int
    name: str
    display_name: str
    color: str | None
    score_value: float


class TaskSummary(ApiModel):
    id: int
    title: str
    finished_at: UtcDateTime | None
    abandoned_at: UtcDateTime | None = None
    abandoned_by_task_id: int | None = None
    unfinished_descendant_count: int = 0


class BlockRead(ApiModel):
    id: int
    reason: str | None
    blocking_task_id: int | None
    blocking_task: TaskSummary | None
    blocked_at: UtcDateTime
    unblocked_at: UtcDateTime | None


class TaskCreate(ApiModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    priority: int = Field(default=1, ge=1)
    due_date: date | None = None
    last_worked_at: UtcDateTime | None = None
    parent_task_id: int | None = None
    tag_ids: list[int] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return clean_required(value)


class TaskUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    priority: int | None = Field(default=None, ge=1)
    due_date: date | None = None
    last_worked_at: UtcDateTime | None = None
    parent_task_id: int | None = None
    tag_ids: list[int] | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return clean_required(value) if value is not None else None


class TaskRead(ApiModel):
    id: int
    user_id: int
    title: str
    description: str | None
    priority: int
    due_date: date | None
    last_worked_at: UtcDateTime | None
    finished_at: UtcDateTime | None
    abandoned_at: UtcDateTime | None
    abandoned_by_task_id: int | None
    parent_task_id: int | None
    parent_task: TaskSummary | None
    unfinished_descendant_count: int
    created_at: UtcDateTime
    updated_at: UtcDateTime
    score: float
    scoring_warning: str | None
    scoring_warning_code: str | None = None
    scoring_warning_params: dict[str, object] = Field(default_factory=dict)
    ranking_score: float
    ranking_source_task_id: int | None
    ranking_source_score: float | None
    direct_tags: list[TagSummary]
    inherited_tags: list[TagSummary]
    current_block: BlockRead | None
    active_blocks: list[BlockRead]
    blocking_history: list[BlockRead]
    blocks_tasks: list[TaskSummary]
    subtasks: list[TaskSummary]


class BlockCreate(ApiModel):
    reason: str | None = Field(default=None, min_length=1, max_length=4000)
    blocking_task_id: int | None = None
    unblocked_at: UtcDateTime | None = None

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return clean_required(value) if value is not None else None

    @model_validator(mode="after")
    def validate_kind(self) -> "BlockCreate":
        if (self.reason is None) == (self.blocking_task_id is None):
            raise ValueError(localized("api.chooseEitherABlockingTaskOrAManualReason"))
        if self.blocking_task_id is not None and self.unblocked_at is not None:
            raise ValueError(localized("api.taskBlockersCannotAutoUnblock"))
        return self


class BlockReblock(ApiModel):
    unblocked_at: UtcDateTime | None = None


class TagCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=32)
    score_value: float = Field(default=0, allow_inf_nan=False)
    parent_tag_id: int | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return clean_required(value, tag=True)


class TagUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=32)
    score_value: float | None = Field(default=None, allow_inf_nan=False)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return clean_required(value, tag=True) if value is not None else None

    @model_validator(mode="after")
    def require_score_value_when_supplied(self) -> "TagUpdate":
        if "score_value" in self.model_fields_set and self.score_value is None:
            raise ValueError(localized("api.tagValueCannotBeNull"))
        return self


class TagRead(TagSummary):
    description: str | None
    direct_task_count: int
    parents: list[TagSummary]
    children: list[TagSummary]
    ancestors: list[TagSummary]


class TagRelationshipCreate(ApiModel):
    parent_tag_id: int


class TagMergeCreate(ApiModel):
    destination_tag_id: int


class TagMergePreview(ApiModel):
    source_tag_id: int
    destination_tag_id: int
    task_assignments: int
    parent_relationships: int
    child_relationships: int
