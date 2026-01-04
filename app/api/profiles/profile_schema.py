"""Schemas for resource profiles."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ResourceProfileBase(BaseModel):
    """Base schema for resource profile."""

    skills: str | None = None
    domains: str | None = None


class ResourceProfileCreate(ResourceProfileBase):
    """Schema for creating a resource profile."""

    user_id: uuid.UUID


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

    # Skills & Domains
    skills: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)

    # Workload
    jira_workload: int = 0
    github_workload: int = 0
    total_workload: int = 0
    workload_updated_at: datetime | None = None

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProfileWorkload(BaseModel):
    """Workload metrics for a profile."""

    user_id: uuid.UUID
    display_name: str | None = None
    jira_workload: int = 0
    github_workload: int = 0
    total_workload: int = 0
    last_updated: datetime | None = None


class UpdateSkillsRequest(BaseModel):
    """Request to update skills/domains."""

    skills: list[str] | None = None
    domains: list[str] | None = None
