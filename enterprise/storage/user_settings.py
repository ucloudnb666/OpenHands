from datetime import datetime
from typing import Any

from server.constants import DEFAULT_BILLING_MARGIN
from sqlalchemy import DateTime, Identity, String
from sqlalchemy.orm import Mapped, mapped_column
from storage.base import Base


class UserSettings(Base):
    __tablename__ = 'user_settings'

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    keycloak_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    max_iterations: Mapped[int | None] = mapped_column(nullable=True)
    security_analyzer: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmation_mode: Mapped[bool | None] = mapped_column(nullable=True, default=False)
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_api_key: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_api_key_for_byor: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    remote_runtime_resource_factor: Mapped[int | None] = mapped_column(nullable=True)
    enable_default_condenser: Mapped[bool] = mapped_column(nullable=False, default=True)
    condenser_max_size: Mapped[int | None] = mapped_column(nullable=True)
    user_consents_to_analytics: Mapped[bool | None] = mapped_column(nullable=True)
    billing_margin: Mapped[float | None] = mapped_column(nullable=True, default=DEFAULT_BILLING_MARGIN)
    enable_sound_notifications: Mapped[bool | None] = mapped_column(nullable=True, default=False)
    enable_proactive_conversation_starters: Mapped[bool] = mapped_column(
        nullable=False, default=True
    )
    sandbox_base_container_image: Mapped[str | None] = mapped_column(String, nullable=True)
    sandbox_runtime_container_image: Mapped[str | None] = mapped_column(String, nullable=True)
    sandbox_grouping_strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    user_version: Mapped[int] = mapped_column(nullable=False, default=0)
    accepted_tos: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mcp_config: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    disabled_skills: Mapped[list[str] | None] = mapped_column(nullable=True)
    search_api_key: Mapped[str | None] = mapped_column(String, nullable=True)
    sandbox_api_key: Mapped[str | None] = mapped_column(String, nullable=True)
    max_budget_per_task: Mapped[float | None] = mapped_column(nullable=True)
    enable_solvability_analysis: Mapped[bool | None] = mapped_column(nullable=True, default=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    email_verified: Mapped[bool | None] = mapped_column(nullable=True)
    git_user_name: Mapped[str | None] = mapped_column(String, nullable=True)
    git_user_email: Mapped[str | None] = mapped_column(String, nullable=True)
    v1_enabled: Mapped[bool | None] = mapped_column(nullable=True)
    already_migrated: Mapped[bool | None] = mapped_column(
        nullable=True, default=False
    )  # False = not migrated, True = migrated
