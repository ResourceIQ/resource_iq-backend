"""Jira integration Pydantic schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class JiraIssueStatus(str, Enum):
    """Common Jira issue statuses."""

    TO_DO = "To Do"
    IN_PROGRESS = "In Progress"
    IN_REVIEW = "In Review"
    DONE = "Done"
    CLOSED = "Closed"
    OPEN = "Open"


class JiraUser(BaseModel):
    """Schema for Jira user information."""

    account_id: str = Field(..., description="Jira account ID")
    display_name: str | None = Field(default=None, description="User display name")
    email_address: str | None = Field(default=None, description="User email address")
    avatar_url: HttpUrl | None = Field(default=None, description="User avatar URL")
    active: bool = Field(default=True, description="Whether user is active")


class JiraComment(BaseModel):
    """Schema for Jira issue comments."""

    id: str
    author: JiraUser
    body: str
    created: datetime
    updated: datetime | None = None


class JiraIssueContent(BaseModel):
    """Schema for Jira issue content with context for embeddings."""

    issue_id: str
    issue_key: str
    project_key: str
    summary: str
    description: str | None = None
    issue_type: str
    status: str
    priority: str | None = None
    labels: list[str] = Field(default_factory=list)
    assignee: JiraUser | None = None
    reporter: JiraUser | None = None
    issue_url: HttpUrl
    comments: list[JiraComment] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_at: datetime | None = None

    # Generated context for NLP processing
    context: str | None = None

    class Config:
        populate_by_name = True


class JiraSyncRequest(BaseModel):
    """Request schema for manual Jira sync."""

    project_keys: list[str] | None = Field(
        default=None, description="Specific projects to sync. If None, syncs all."
    )
    max_results: int = Field(
        default=100, ge=1, le=1000, description="Maximum issues to fetch per project"
    )
    include_closed: bool = Field(
        default=True, description="Include closed/done issues"
    )
    sync_comments: bool = Field(
        default=True, description="Include issue comments"
    )
    generate_embeddings: bool = Field(
        default=True, description="Generate embeddings for NLP"
    )


class JiraSyncResponse(BaseModel):
    """Response schema for Jira sync operation."""

    status: str
    projects_synced: list[str]
    issues_synced: int
    issues_updated: int
    issues_created: int
    embeddings_generated: int
    errors: list[str] = Field(default_factory=list)
    sync_duration_seconds: float


class JiraWebhookEvent(BaseModel):
    """Schema for Jira webhook event payload."""

    webhook_event: str = Field(..., alias="webhookEvent")
    issue_event_type_name: str | None = Field(default=None, alias="issue_event_type_name")
    timestamp: int | None = None
    issue: dict | None = None
    user: dict | None = None
    changelog: dict | None = None

    class Config:
        populate_by_name = True


class DeveloperWorkload(BaseModel):
    """Schema for developer workload calculation (FR8)."""

    jira_account_id: str
    display_name: str | None
    email: str | None

    # Workload metrics
    open_issues: int = Field(default=0, description="Issues with status 'Open' or 'To Do'")
    in_progress_issues: int = Field(default=0, description="Issues with status 'In Progress'")
    in_review_issues: int = Field(default=0, description="Issues with status 'In Review'")
    total_active_issues: int = Field(default=0, description="Total active issues")

    # Breakdown by priority
    high_priority_count: int = Field(default=0, description="High/Highest priority issues")
    medium_priority_count: int = Field(default=0, description="Medium priority issues")
    low_priority_count: int = Field(default=0, description="Low/Lowest priority issues")

    # Breakdown by issue type
    bugs_count: int = Field(default=0)
    tasks_count: int = Field(default=0)
    stories_count: int = Field(default=0)
    other_count: int = Field(default=0)

    # Calculated workload score (higher = more busy)
    workload_score: float = Field(
        default=0.0,
        description="Weighted workload score based on priority and issue type"
    )

    last_updated: datetime | None = None


class UserMappingRequest(BaseModel):
    """Request schema for mapping Jira user to internal profile."""

    jira_account_id: str
    internal_user_id: str | None = None
    github_login: str | None = None


class UserMappingResponse(BaseModel):
    """Response schema for user mapping."""

    jira_account_id: str
    jira_display_name: str | None
    jira_email: str | None
    github_login: str | None
    github_id: int | None
    internal_user_id: str | None
    mapped: bool

