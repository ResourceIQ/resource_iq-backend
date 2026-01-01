from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.integrations.GitHub.github_schema import GitHubUser, PullRequestContent
from app.api.integrations.GitHub.github_service import GithubIntegrationService
from app.utils.deps import SessionDep

router = APIRouter(prefix="/github", tags=["github"])


@router.get("/get_developers")
async def get_developers(session: SessionDep) -> list[dict[str, Any]]:
    try:
        github_manager = GithubIntegrationService(session)
        return github_manager.get_all_org_members()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/get_closed_prs_context_per_author")
async def get_closed_prs_context_per_author(
    session: SessionDep, author: GitHubUser
) -> list[PullRequestContent]:
    try:
        github_manager = GithubIntegrationService(session)
        return github_manager.get_org_closed_prs_context_by_author(author=author)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/get_closed_prs_context_all_authors")
async def get_closed_prs_context_all_authors(
    session: SessionDep,
) -> dict[str, list[PullRequestContent]]:
    try:
        github_manager = GithubIntegrationService(session)
        return github_manager.get_org_closed_prs_context_all_authors()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
