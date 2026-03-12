"""Jira integration database models."""

from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class JiraOrgIntegration(SQLModel, table=True):
    """Model for storing Jira organization integration credentials."""

    __tablename__ = "org_integrations_jira"

    id: int | None = Field(default=None, primary_key=True)
    jira_url: str = Field(..., description="Jira instance URL")
    jira_email: str = Field(..., description="Email associated with API token")
    project_keys: str | None = Field(
        default=None, description="Comma-separated list of project keys to sync"
    )
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)


class JiraOAuthToken(SQLModel, table=True):
    """Stores Atlassian OAuth tokens for Jira Cloud access."""

    __tablename__ = "jira_oauth_tokens"

    id: int | None = Field(default=None, primary_key=True)
    cloud_id: str | None = Field(
        default=None, index=True, description="Atlassian cloud/site identifier"
    )
    jira_site_url: str | None = Field(
        default=None,
        description="Base URL for the Jira site (from accessible-resources)",
    )
    access_token: str = Field(..., description="Bearer access token")
    refresh_token: str | None = Field(default=None, description="Refresh token")
    expires_at: datetime = Field(..., description="Access token expiry (UTC)")
    scope: str | None = Field(
        default=None, description="Space-separated scopes granted by Atlassian"
    )
    token_type: str | None = Field(default="Bearer", description="Token type")
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)


class JiraIssueTypeStatus(SQLModel, table=True):
    """Per-issue-type configuration for embedding eligibility.

    For each Jira issue type the admin selects which workflow statuses
    qualify an issue for embedding.  Only issues whose current status
    appears in ``selected_statuses`` are embedded into the vector store.
    """

    __tablename__ = "jira_issue_type_statuses"

    id: int | None = Field(default=None, primary_key=True)
    issue_type_id: str = Field(
        ..., unique=True, index=True, description="Jira issue type ID"
    )
    issue_type_name: str = Field(..., description="Human-readable name (e.g. Bug)")
    available_statuses: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
        description="All workflow statuses available for this issue type",
    )
    selected_statuses: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
        description="Statuses that qualify issues of this type for embedding",
    )
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)
