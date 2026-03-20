from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class GitHubUser(BaseModel):
    login: str
    id: int
    email: str | None = None
    name: str | None = None
    avatar_url: HttpUrl | None = None
    html_url: HttpUrl | None = None


class GitHubDeveloperStats(GitHubUser):

    merged_prs: int = 0
    reviewed_prs: int = 0


class PullRequestContent(BaseModel):
    id: int
    number: int
    title: str
    body: str | None = None
    context: str | None = None
    repo_id: int
    repo_name: str | None = None
    labels: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(
        default_factory=list,
        description="List of changed file paths",
    )
    html_url: HttpUrl

    author: GitHubUser = Field(..., description="The author of the pull request")

    class Config:
        populate_by_name = True


# ── GitHub App Connection Schemas ────────────────────────────────


class GitHubAppConnectResponse(BaseModel):
    """Response containing the GitHub App installation URL."""

    install_url: str
    app_slug: str | None = None


class GitHubAppConnectionStatus(BaseModel):
    """Connection status of the GitHub App installation."""

    connected: bool
    message: str | None = None
    org_name: str | None = None
    installation_id: str | None = None
    install_url: str | None = None
    repositories_count: int | None = None


class GitHubRepository(BaseModel):
    """Schema for a GitHub repository."""

    id: int
    name: str
    full_name: str
    private: bool
    html_url: HttpUrl
    description: str | None = None
    default_branch: str = "main"
    language: str | None = None
    stargazers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    branch_count: int = 0
    pull_request_count: int = 0
    open_pr_count: int = 0
    closed_pr_count: int = 0
    merged_pr_count: int = 0
    stale_pr_count: int = 0
    real_issue_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pushed_at: datetime | None = None
    last_commit_at: datetime | None = None
    latest_workflow_status: str | None = None  # success, failure, in_progress, etc.
    languages: dict[str, int] = Field(default_factory=dict)
    contributors: list["GitHubContributor"] = Field(default_factory=list)


class GitHubContributor(BaseModel):
    """Schema for a GitHub Contributor."""

    login: str
    id: int
    avatar_url: HttpUrl | None = None
    contributions: int = 0


class GitHubSyncRequest(BaseModel):
    """Request schema for GitHub PR sync."""

    repo_names: list[str] | None = Field(
        default=None,
        description="Specific repos to sync (name, not full_name). If None, syncs all.",
    )
    max_prs_per_repo: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum PRs to fetch per repo",
    )
    include_open: bool = Field(default=False, description="Include open PRs")
    generate_embeddings: bool = Field(
        default=True, description="Generate embeddings for NLP"
    )


class GitHubSyncResponse(BaseModel):
    """Response schema for GitHub sync operation."""

    status: str
    repos_synced: list[str]
    prs_synced: int
    prs_created: int
    prs_updated: int
    embeddings_generated: int
    errors: list[str] = Field(default_factory=list)
    sync_duration_seconds: float
