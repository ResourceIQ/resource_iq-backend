"""Vector search and sync API routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.embedding.embedding_sync_service import (
    SyncAllRequest,
    SyncAllResponse,
    run_sync_all_vectors,
)
from app.api.integrations.GitHub.github_service import GithubIntegrationService
from app.api.user.user_model import Role
from app.utils.deps import RoleChecker, SessionDep

router = APIRouter(prefix="/vectors", tags=["Vector Embeddings"])


@router.post("/sync/author",dependencies=[Depends(RoleChecker([Role.ADMIN,Role.MODERATOR]))])
async def sync_author_vectors(
    session: SessionDep,
    author_login: str,
    max_prs: int = 100,
) -> dict[str, Any]:
    """Sync PR vectors for a specific author."""
    try:
        service = GithubIntegrationService(session)
        # Get org members to find matching user
        members = service.get_all_org_members()
        author = next((m for m in members if m.login == author_login), None)

        if not author:
            raise HTTPException(status_code=404, detail="Author not found")

        result = service.sync_author_prs_to_vectors(author, max_prs)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/all", response_model=SyncAllResponse,dependencies=[Depends(RoleChecker([Role.ADMIN,Role.MODERATOR]))])
async def sync_all_vectors(
    session: SessionDep,
    request: SyncAllRequest | None = None,
) -> SyncAllResponse:
    """
    Sync vectors from both GitHub PRs and Jira issues.

    This endpoint fetches data from configured integrations and generates
    embeddings for semantic search and recommendation engine.

    **Optional Parameters (via request body):**
    - `sync_github`: Enable/disable GitHub sync (default: true)
    - `sync_jira`: Enable/disable Jira sync (default: true)
    - `github_max_prs_per_author`: Max PRs per author (default: 50)
    - `jira_project_keys`: Specific Jira projects (default: all)
    - `jira_max_issues`: Max issues per project (default: 100)
    - `jira_include_closed`: Include closed issues (default: true)
    - `jira_sync_comments`: Sync issue comments (default: true)

    **Example request body:**
    ```json
    {
        "sync_github": true,
        "sync_jira": true,
        "github_max_prs_per_author": 50,
        "jira_max_issues": 100
    }
    ```
    """
    request = request or SyncAllRequest()
    return run_sync_all_vectors(session=session, request=request)


class UnifiedSearchRequest(BaseModel):
    """Request schema for unified search across all sources."""

    query: str = Field(..., description="Search query text")
    n_results: int = Field(
        default=10, ge=1, le=100, description="Max results to return"
    )

    # Source selection
    search_github: bool = Field(default=True, description="Search GitHub PRs")
    search_jira: bool = Field(default=True, description="Search Jira issues")

    # Filters
    github_author_login: str | None = Field(
        default=None, description="Filter GitHub results by author"
    )
    jira_project_key: str | None = Field(
        default=None, description="Filter Jira results by project"
    )
    jira_assignee_id: str | None = Field(
        default=None, description="Filter Jira results by assignee"
    )


class SearchResult(BaseModel):
    """Individual search result."""

    source: str  # "github" or "jira"
    id: str
    title: str
    url: str | None = None
    author: str | None = None
    context: str
    created_at: str | None = None


class UnifiedSearchResponse(BaseModel):
    """Response schema for unified search."""

    query: str
    total_results: int
    github_results: int
    jira_results: int
    results: list[SearchResult]
