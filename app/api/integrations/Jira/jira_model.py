"""Jira integration database models."""

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import JSON, Column, Text
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


class JiraIssueVector(SQLModel, table=True):
    """Model for storing Jira issue embeddings for NLP/similarity search."""

    __tablename__ = "jira_issue_vectors"

    model_config = {"arbitrary_types_allowed": True}

    id: int | None = Field(default=None, primary_key=True)
    issue_id: str = Field(unique=True, index=True)
    issue_key: str = Field(index=True)
    project_key: str = Field(index=True)
    assignee_account_id: str | None = Field(default=None, index=True)

    # Vector embedding for similarity search
    embedding: Vector = Field(sa_column=Column(Vector(dim=1536)))

    # Original context text used for embedding
    context: str = Field(sa_column=Column(Text))
    metadata_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

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
