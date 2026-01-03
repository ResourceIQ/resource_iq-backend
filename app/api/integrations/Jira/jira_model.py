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


class JiraIssue(SQLModel, table=True):
    """Model for storing Jira issues."""

    __tablename__ = "jira_issues"

    id: int | None = Field(default=None, primary_key=True)
    issue_id: str = Field(unique=True, index=True, description="Jira issue ID")
    issue_key: str = Field(index=True, description="Jira issue key (e.g., PROJ-123)")
    project_key: str = Field(index=True, description="Project key")
    summary: str = Field(..., description="Issue summary/title")
    description: str | None = Field(
        default=None, sa_column=Column(Text), description="Issue description"
    )
    issue_type: str = Field(..., description="Issue type (Bug, Task, Story, etc.)")
    status: str = Field(index=True, description="Issue status")
    priority: str | None = Field(default=None, description="Issue priority")
    labels: str | None = Field(
        default=None, description="Comma-separated list of labels"
    )

    # Assignee information
    assignee_account_id: str | None = Field(
        default=None, index=True, description="Jira account ID of assignee"
    )
    assignee_display_name: str | None = Field(
        default=None, description="Display name of assignee"
    )
    assignee_email: str | None = Field(default=None, description="Email of assignee")

    # Reporter information
    reporter_account_id: str | None = Field(
        default=None, description="Jira account ID of reporter"
    )
    reporter_display_name: str | None = Field(
        default=None, description="Display name of reporter"
    )

    # URLs and links
    issue_url: str = Field(..., description="URL to the Jira issue")

    # Timestamps from Jira
    jira_created_at: datetime | None = Field(
        default=None, description="When issue was created in Jira"
    )
    jira_updated_at: datetime | None = Field(
        default=None, description="When issue was last updated in Jira"
    )
    jira_resolved_at: datetime | None = Field(
        default=None, description="When issue was resolved in Jira"
    )

    # Local timestamps
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)

    # Comments stored as JSON
    comments_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON), description="Issue comments"
    )


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


class DeveloperProfile(SQLModel, table=True):
    """
    Model for mapping Jira users to internal ResourceIQ profiles.
    Satisfies UC-002: User Mapping requirement.
    """

    __tablename__ = "developer_profiles"

    id: int | None = Field(default=None, primary_key=True)

    # Jira account information
    jira_account_id: str | None = Field(
        default=None, unique=True, index=True, description="Jira account ID"
    )
    jira_display_name: str | None = Field(default=None, description="Jira display name")
    jira_email: str | None = Field(default=None, description="Jira email")

    # GitHub account information (for cross-platform mapping)
    github_login: str | None = Field(
        default=None, unique=True, index=True, description="GitHub username"
    )
    github_id: int | None = Field(default=None, description="GitHub user ID")

    # Internal ResourceIQ user ID (links to User table)
    internal_user_id: str | None = Field(
        default=None, index=True, description="ResourceIQ internal user UUID"
    )

    # Developer skills and domains (extracted from NLP analysis)
    skills: str | None = Field(
        default=None, description="Comma-separated list of skills"
    )
    domains: str | None = Field(
        default=None, description="Comma-separated list of domains"
    )

    # Workload metrics
    current_workload: int = Field(
        default=0, description="Number of open/in-progress issues"
    )
    workload_updated_at: datetime | None = Field(
        default=None, description="When workload was last calculated"
    )

    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)

