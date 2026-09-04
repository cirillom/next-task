from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeminiSettingsRead(StrictModel):
    configured: bool
    masked_key: str | None
    model: str


class GeminiKeyUpdate(StrictModel):
    api_key: str = Field(min_length=20, max_length=512)

    @field_validator("api_key", mode="before")
    @classmethod
    def clean_api_key(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class TextToTaskRequest(StrictModel):
    text: str = Field(min_length=1, max_length=12_000)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Text cannot be blank")
        return cleaned


class GeneratedTask(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20_000)
    status_name: str = Field(min_length=1, max_length=80)
    priority: int = Field(ge=1, le=5)
    due_date: date | None
    assignee_emails: list[str] = Field(max_length=20)
    tag_names: list[str] = Field(max_length=12)

    @field_validator("title", "status_name")
    @classmethod
    def clean_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be blank")
        return cleaned


class TextToTaskDraft(StrictModel):
    title: str
    description: str | None
    status_id: int
    priority: int
    due_date: date | None
    assignee_ids: list[int]
    existing_tag_ids: list[int]
    new_tag_names: list[str]
    model: str
