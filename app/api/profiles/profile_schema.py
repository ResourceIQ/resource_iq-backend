"""Schemas for resource profiles."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.api.integrations.GitHub.github_schema import GitHubUser
from app.api.integrations.Jira.jira_schema import JiraUser


class ResourceProfileBase(BaseModel):
    """Base schema for resource profile."""

    position_id: int | None = None


class ResourceProfileCreate(ResourceProfileBase):
    """Schema for creating a resource profile."""

    user_id: uuid.UUID
    phone_number: str | None = None
    address: str | None = None


class JiraConnectionRequest(BaseModel):
    """Request to connect Jira account to profile."""

    jira_account_id: str
    jira_display_name: str | None = None
    jira_email: str | None = None
    jira_avatar_url: str | None = None


class GitHubConnectionRequest(BaseModel):
    """Request to connect GitHub account to profile."""

    github_id: int | None = None
    github_login: str
    github_display_name: str | None = None
    github_email: str | None = None
    github_avatar_url: str | None = None


class ResourceProfileResponse(BaseModel):
    """Response schema for resource profile."""

    id: int
    user_id: uuid.UUID
    phone_number: str | None = None
    address: str | None = None
    position_id: int | None = None
    position: str | None = None

    # Jira

    jira_account_id: str | None = None
    jira_display_name: str | None = None
    jira_email: str | None = None
    jira_avatar_url: str | None = None
    jira_connected_at: datetime | None = None
    has_jira: bool = False

    # GitHub
    github_id: int | None = None
    github_login: str | None = None
    github_display_name: str | None = None
    github_email: str | None = None
    github_avatar_url: str | None = None
    github_connected_at: datetime | None = None
    has_github: bool = False

    burnout_level: float = 0.0

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProfileWorkload(BaseModel):
    """Workload metrics for a profile."""

    user_id: uuid.UUID
    display_name: str | None = None
    jira_workload: int = 0
    total_workload: int = 0
    last_updated: datetime | None = None


class UpdateSkillsRequest(BaseModel):
    """Request to update position only."""

    position_id: int | None = None


class UpdateProfileRequest(BaseModel):
    """Request to partially update a profile."""

    burnout_level: float | None = Field(default=None, ge=0.0, le=10.0)
    position_id: int | None = None

    jira_account_id: str | None = None
    jira_display_name: str | None = None
    jira_email: str | None = None
    jira_avatar_url: str | None = None

    github_id: int | None = None
    github_login: str | None = None
    github_display_name: str | None = None
    github_email: str | None = None
    github_avatar_url: str | None = None


class UpdateMyProfileRequest(UpdateProfileRequest):
    """Request to partially update the current user's profile."""


class ProfileMatchResponse(BaseModel):
    """Response schema for a matched Jira/GitHub profile pair."""

    github_account: GitHubUser
    jira_account: JiraUser | None = None
    match_score: float
