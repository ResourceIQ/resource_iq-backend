"""Reusable embedding sync workflow shared by sync endpoints and background tasks."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.integrations.GitHub.github_service import GithubIntegrationService


class SyncAllRequest(BaseModel):
    """Request schema for syncing all vectors from GitHub and Jira."""

    sync_github: bool = Field(default=True, description="Sync GitHub PRs")
    sync_jira: bool = Field(default=True, description="Sync Jira issues")
    github_max_prs_per_author: int = Field(
        default=50, ge=1, le=500, description="Max PRs to fetch per GitHub author"
    )
    jira_project_keys: list[str] | None = Field(
        default=None, description="Specific Jira projects to sync (None = all)"
    )
    jira_max_issues: int = Field(
        default=100, ge=1, le=1000, description="Max Jira issues to fetch per project"
    )
    jira_include_closed: bool = Field(
        default=True, description="Include closed/done Jira issues"
    )
    jira_sync_comments: bool = Field(
        default=True, description="Sync Jira issue comments"
    )


class SyncAllResponse(BaseModel):
    """Response schema for sync all operation."""

    status: str
    github: dict[str, Any] | None = None
    jira: dict[str, Any] | None = None
    total_embeddings: int
    errors: list[str] = Field(default_factory=list)


def run_sync_all_vectors(
    session: Session,
    request: SyncAllRequest,
    progress_callback: Callable[[int, str], None] | None = None,
) -> SyncAllResponse:
    """Run the full GitHub + Jira vector sync flow with optional progress updates."""

    def emit(progress: int, log_message: str) -> None:
        if progress_callback:
            progress_callback(progress, log_message)

    errors: list[str] = []
    github_result: dict[str, Any] | None = None
    jira_result: dict[str, Any] | None = None
    total_embeddings = 0

    enabled_steps = int(request.sync_github) + int(request.sync_jira)
    progress = 5

    emit(progress, "Starting embedding sync workflow")

    if request.sync_github:
        try:
            emit(progress + 10, "Syncing GitHub pull requests")
            github_service = GithubIntegrationService(session)
            github_result = github_service.sync_all_authors_prs_to_vectors(
                request.github_max_prs_per_author
            )
            total_embeddings += github_result.get("total_prs", 0)
            emit(progress + 35, "GitHub sync completed")
        except Exception as exc:
            error_msg = f"GitHub sync failed: {exc}"
            errors.append(error_msg)
            emit(progress + 35, error_msg)
        progress += 45 if enabled_steps > 1 else 80

    if request.sync_jira:
        try:
            emit(progress + 5, "Syncing Jira issues")
            from app.api.integrations.Jira.jira_service import JiraIntegrationService

            jira_service = JiraIntegrationService(session)
            sync_result = jira_service.sync_issues(
                project_keys=request.jira_project_keys,
                max_results=request.jira_max_issues,
                include_closed=request.jira_include_closed,
                sync_comments=request.jira_sync_comments,
                generate_embeddings=True,
            )
            jira_result = {
                "status": sync_result.status,
                "projects_synced": sync_result.projects_synced,
                "issues_synced": sync_result.issues_synced,
                "embeddings_generated": sync_result.embeddings_generated,
                "duration_seconds": sync_result.sync_duration_seconds,
            }
            total_embeddings += sync_result.embeddings_generated
            if sync_result.errors:
                errors.extend(sync_result.errors)
            emit(90, "Jira sync completed")
        except Exception as exc:
            error_msg = f"Jira sync failed: {exc}"
            errors.append(error_msg)
            emit(90, error_msg)

    if not errors:
        status = "completed"
    elif github_result or jira_result:
        status = "completed_with_errors"
    else:
        status = "failed"

    emit(100, f"Embedding sync finished with status: {status}")

    return SyncAllResponse(
        status=status,
        github=github_result,
        jira=jira_result,
        total_embeddings=total_embeddings,
        errors=errors,
    )
