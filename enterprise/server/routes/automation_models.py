"""Pydantic request/response models for automation CRUD API."""

from pydantic import BaseModel, Field


class CreateAutomationRequest(BaseModel):
    """Simple mode (Phase 1): form input → generated file."""

    name: str = Field(min_length=1, max_length=200)
    schedule: str  # 5-field cron expression
    timezone: str = 'UTC'
    prompt: str = Field(min_length=1)
    repository: str | None = None  # e.g., "owner/repo"
    branch: str | None = None


class UpdateAutomationRequest(BaseModel):
    name: str | None = None
    schedule: str | None = None
    timezone: str | None = None
    prompt: str | None = None
    repository: str | None = None
    branch: str | None = None
    enabled: bool | None = None


class AutomationResponse(BaseModel):
    id: str
    name: str
    enabled: bool
    trigger_type: str
    config: dict
    file_url: str | None = None
    last_triggered_at: str | None = None
    created_at: str
    updated_at: str


class AutomationRunResponse(BaseModel):
    id: str
    automation_id: str
    conversation_id: str | None = None
    status: str
    error_detail: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str


class PaginatedAutomationsResponse(BaseModel):
    items: list[AutomationResponse]
    total: int
    next_page_id: str | None = None


class PaginatedRunsResponse(BaseModel):
    items: list[AutomationRunResponse]
    total: int
    next_page_id: str | None = None
