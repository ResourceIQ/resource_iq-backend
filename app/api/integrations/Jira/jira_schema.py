"""Jira integration Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class JiraAuthConnectResponse(BaseModel):
    """Response for initiating Atlassian OAuth connect."""

    auth_url: HttpUrl
    state: str


class JiraAuthCallbackResponse(BaseModel):
    """Response after completing OAuth callback."""

    status: str
    cloud_id: str | None = None
    jira_site_url: HttpUrl | None = None
    expires_at: datetime | None = None
    scope: str | None = None


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
    include_closed: bool = Field(default=True, description="Include closed/done issues")
    sync_comments: bool = Field(default=True, description="Include issue comments")
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


class JiraIssueTypeStatusResponse(BaseModel):
    """Response for a single issue type with its status configuration."""

    id: int
    issue_type_id: str
    issue_type_name: str
    available_statuses: list[str] = Field(default_factory=list)
    selected_statuses: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class JiraIssueTypeStatusUpdateRequest(BaseModel):
    """Request to update which statuses qualify for embedding on an issue type."""

    selected_statuses: list[str] = Field(
        ...,
        description="Statuses that qualify issues of this type for embedding",
    )


class JiraCreateIssueRequest(BaseModel):
    """Request schema for creating a Jira issue."""

    project_key: str = Field(..., description="Jira project key (e.g. PROJ)")
    summary: str = Field(..., description="Issue summary / title")
    description: str | None = Field(default=None, description="Issue description")
    issue_type: str = Field(default="Task", description="Issue type name")
    assignee_user_id: str | None = Field(
        default=None,
        description="ResourceIQ user_id (UUID) to assign. Resolved to jira_account_id internally.",
    )


class JiraCreateIssueResponse(BaseModel):
    """Response schema for a newly created Jira issue."""

    issue_key: str = Field(..., description="Created issue key (e.g. PROJ-42)")
    issue_url: str = Field(..., description="Browse URL for the issue")
    summary: str
    assigned_to: str | None = Field(
        default=None, description="Display name of the assignee"
    )


class JiraAssignIssueRequest(BaseModel):
    """Request schema for assigning / reassigning a Jira issue."""

    assignee_user_id: str = Field(
        ...,
        description="ResourceIQ user_id (UUID) to assign.",
    )


class JiraIssueDetailResponse(BaseModel):
    """Response for fetching a single Jira issue's details."""

    issue_key: str
    issue_url: str
    summary: str
    description: str | None = None
    assigned_to: str | None = None
    status: str
    issue_type: str


class JiraAssignIssueResponse(BaseModel):
    """Response after assigning a Jira issue."""

    issue_key: str
    assigned_to: str | None = Field(
        default=None, description="Display name of the new assignee"
    )


class JiraProjectStats(BaseModel):
    """Real-time task count for a single Jira project."""

    key: str
    name: str
    task_count: int


class JiraAssigneeStats(BaseModel):
    """Real-time task count for a single Jira assignee."""

    account_id: str
    display_name: str
    avatar_url: HttpUrl | None = None
    task_count: int


class JiraLiveStatsResponse(BaseModel):
    """Aggregated real-time Jira task statistics."""

    total_active_tasks: int
    unassigned_tasks: int
    tasks_by_project: list[JiraProjectStats]
    tasks_by_status: dict[str, int]
    tasks_by_priority: dict[str, int]
    top_assignees: list[JiraAssigneeStats]


class JiraDeveloperStats(JiraUser):
    """Real-time task statistics for a specific Jira user."""

    todo_tickets: int = Field(default=0, description="Number of tickets in 'To Do' status")
    inprogress_tickets: int = Field(default=0, description="Number of tickets in 'In Progress' status")
    pr_review_tickets: int = Field(default=0, description="Number of tickets in 'PR Review' status")
    done_tickets: int = Field(default=0, description="Number of tickets in 'Done' status")
    solved_tickets: int = Field(
        default=0, description="Number of tickets with 'Done' status category"
    )
    active_tickets: int = Field(
        default=0, description="Number of tickets not in 'Done' status category"
    )
    total_tickets: int = Field(default=0, description="Total number of tickets assigned")
    bugs_reported: int = Field(default=0, description="Number of tickets with type 'Bug' reported by this user")
