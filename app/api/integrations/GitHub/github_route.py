from typing import Any

from fastapi import APIRouter, HTTPException

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


@router.get("/get_closed_prs_context")
async def get_closed_prs_context(session: SessionDep) -> list[str]:
    try:
        github_manager = GithubIntegrationService(session)
        return github_manager.get_org_closed_prs_context()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
