"""Vector search and sync API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.integrations.GitHub.github_service import GithubIntegrationService
from app.utils.deps import SessionDep

router = APIRouter(prefix="/vectors", tags=["Vector Embeddings"])


class SyncAllRequest(BaseModel):
    """Request schema for syncing all vectors from GitHub and Jira."""

    # Source selection (all enabled by default)
    sync_github: bool = Field(default=True, description="Sync GitHub PRs")
    sync_jira: bool = Field(default=True, description="Sync Jira issues")

    # GitHub options
    github_max_prs_per_author: int = Field(
        default=50, ge=1, le=500, description="Max PRs to fetch per GitHub author"
    )

    # Jira options
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


@router.post("/sync/author")
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


@router.post("/sync/all", response_model=SyncAllResponse)
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
    # Use defaults if no request body provided
    if request is None:
        request = SyncAllRequest()

    errors: list[str] = []
    github_result: dict[str, Any] | None = None
    jira_result: dict[str, Any] | None = None
    total_embeddings = 0

    # Sync GitHub PRs
    if request.sync_github:
        try:
            github_service = GithubIntegrationService(session)
            github_result = github_service.sync_all_authors_prs_to_vectors(
                request.github_max_prs_per_author
            )
            total_embeddings += github_result.get("total_prs", 0)
        except Exception as e:
            error_msg = f"GitHub sync failed: {str(e)}"
            errors.append(error_msg)

    # Sync Jira Issues
    if request.sync_jira:
        try:
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
        except Exception as e:
            error_msg = f"Jira sync failed: {str(e)}"
            errors.append(error_msg)

    # Determine overall status
    if not errors:
        status = "completed"
    elif github_result or jira_result:
        status = "completed_with_errors"
    else:
        status = "failed"

    return SyncAllResponse(
        status=status,
        github=github_result,
        jira=jira_result,
        total_embeddings=total_embeddings,
        errors=errors,
    )


@router.post("/search")
async def search_similar_prs(
    session: SessionDep,
    query: str,
    n_results: int = 5,
    author_login: str | None = None,
) -> dict[str, Any]:
    """Search for similar PR contexts (GitHub only)."""
    try:
        service = GithubIntegrationService(session)
        results = service.vector_service.search_similar_prs(
            query, n_results, author_login
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/search/unified", response_model=UnifiedSearchResponse)
async def unified_search(
    session: SessionDep,
    request: UnifiedSearchRequest,
) -> UnifiedSearchResponse:
    """
    Unified semantic search across GitHub PRs and Jira issues.

    This endpoint searches both GitHub and Jira vectors and returns
    combined results sorted by relevance.

    **Request body:**
    - `query`: Search query text (required)
    - `n_results`: Max results to return (default: 10)
    - `search_github`: Include GitHub PRs (default: true)
    - `search_jira`: Include Jira issues (default: true)
    - `github_author_login`: Filter by GitHub author (optional)
    - `jira_project_key`: Filter by Jira project (optional)
    - `jira_assignee_id`: Filter by Jira assignee (optional)
    """
    results: list[SearchResult] = []
    github_count = 0
    jira_count = 0

    # Search GitHub PRs
    if request.search_github:
        try:
            github_service = GithubIntegrationService(session)
            github_results = github_service.vector_service.search_similar_prs(
                request.query,
                request.n_results,
                request.github_author_login,
            )
            for r in github_results:
                results.append(
                    SearchResult(
                        source="github",
                        id=r["pr_id"],
                        title=r["pr_title"],
                        url=r["pr_url"],
                        author=r["author_login"],
                        context=r["context"][:500] if r["context"] else "",
                        created_at=r.get("created_at"),
                    )
                )
            github_count = len(github_results)
        except Exception:
            pass  # GitHub not configured or no results

    # Search Jira Issues
    if request.search_jira:
        try:
            from app.api.integrations.Jira.jira_service import JiraIntegrationService

            jira_service = JiraIntegrationService(session)
            jira_results = jira_service.search_similar_issues(
                request.query,
                request.n_results,
                request.jira_project_key,
                request.jira_assignee_id,
            )
            for r in jira_results:
                results.append(
                    SearchResult(
                        source="jira",
                        id=r["issue_id"],
                        title=r["issue_key"],
                        url=None,  # URL not stored in vector table
                        author=r.get("assignee_account_id"),
                        context=r["context"][:500] if r["context"] else "",
                        created_at=r.get("created_at"),
                    )
                )
            jira_count = len(jira_results)
        except Exception:
            pass  # Jira not configured or no results

    # Limit total results
    results = results[: request.n_results]

    return UnifiedSearchResponse(
        query=request.query,
        total_results=len(results),
        github_results=github_count,
        jira_results=jira_count,
        results=results,
    )
