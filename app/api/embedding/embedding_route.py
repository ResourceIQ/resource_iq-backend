"""Vector search and sync API routes."""

from fastapi import APIRouter, Depends, HTTPException
from app.utils.deps import SessionDep
from app.api.integrations.GitHub.github_service import GithubIntegrationService
from app.api.integrations.GitHub.github_schema import GitHubUser
from app.core.config import settings

router = APIRouter(prefix="/vectors", tags=["Vector Embeddings"])


@router.post("/sync/author")
async def sync_author_vectors(
    session: SessionDep,
    author_login: str,
    max_prs: int = 100,
):
    """Sync PR vectors for a specific author."""
    try:
        service = GithubIntegrationService(session, use_jina_api=settings.USE_JINA_API)
        
        # Get org members to find matching user
        members = service.get_all_org_members()
        author = next((m for m in members if m["login"] == author_login), None)
        
        if not author:
            raise HTTPException(status_code=404, detail="Author not found")
        
        author_obj = GitHubUser(**author)
        result = service.sync_author_prs_to_vectors(author_obj, max_prs)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/all")
async def sync_all_vectors(
    session: SessionDep,
    max_prs_per_author: int = 50,
):
    """Sync PR vectors for all organization members."""
    try:
        service = GithubIntegrationService(session, use_jina_api=settings.USE_JINA_API)
        result = service.sync_all_authors_prs_to_vectors(max_prs_per_author)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_similar_prs(
    session: SessionDep,
    query: str,
    n_results: int = 5,
    author_login: str = None
):
    """Search for similar PR contexts."""
    try:
        service = GithubIntegrationService(session, use_jina_api=settings.USE_JINA_API)
        results = service.vector_service.search_similar_prs(query, n_results, author_login)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
