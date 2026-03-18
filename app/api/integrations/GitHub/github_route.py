"""GitHub integration API routes using GitHub App authentication."""

import logging
import time as time_mod
from typing import Any

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.api.integrations.GitHub.github_model import GithubOrgIntBaseModel
from app.api.integrations.GitHub.github_schema import (
    GitHubAppConnectionStatus,
    GitHubAppConnectResponse,
    GitHubRepository,
    GitHubSyncRequest,
    GitHubSyncResponse,
    GitHubUser,
    PullRequestContent,
)
from app.api.integrations.GitHub.github_service import GithubIntegrationService
from app.api.user.user_model import Role
from app.core.config import settings
from app.utils.deps import RoleChecker, SessionDep

router = APIRouter(prefix="/github", tags=["github"])
logger = logging.getLogger(__name__)


def _generate_app_jwt() -> str:
    """Generate a short-lived JWT signed with the GitHub App private key."""
    if not settings.GITHUB_APP_ID or not settings.GITHUB_PRIVATE_KEY:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: GitHub App ID or Key missing",
        )

    now = int(time_mod.time())
    payload = {
        "iat": now - 60,
        "exp": now + (10 * 60),
        "iss": str(settings.GITHUB_APP_ID),
    }
    return jwt.encode(payload, settings.GITHUB_PRIVATE_KEY, algorithm="RS256")


def _discover_and_store_installation(
    session: SessionDep,
) -> GithubOrgIntBaseModel | None:
    """
    Query GitHub API to discover existing installations and store the first one.
    Only called explicitly from the /auth/connect endpoint.
    """
    try:
        encoded_jwt = _generate_app_jwt()
        resp = httpx.get(
            "https://api.github.com/app/installations",
            headers={
                "Authorization": f"Bearer {encoded_jwt}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(
                "Failed to discover installations: %s %s", resp.status_code, resp.text
            )
            return None

        installations = resp.json()
        if not installations:
            return None

        install = installations[0]
        install_id = str(install["id"])
        org_name = install.get("account", {}).get("login", "unknown")

        existing = session.query(GithubOrgIntBaseModel).first()
        if existing:
            existing.github_install_id = install_id
            existing.org_name = org_name
        else:
            existing = GithubOrgIntBaseModel(
                github_install_id=install_id,
                org_name=org_name,
            )
            session.add(existing)

        session.commit()
        session.refresh(existing)
        logger.info(
            "Auto-discovered GitHub installation: %s (org: %s)", install_id, org_name
        )
        return existing

    except Exception as e:
        logger.error("Failed to auto-discover installation: %s", e)
        return None


# ── Connection / Status Endpoints ────────────────────────────────


@router.get(
    "/auth/connect", dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))]
)
async def connect_github(
    session: SessionDep,
) -> GitHubAppConnectResponse | GitHubAppConnectionStatus:
    """
    Try to auto-discover existing GitHub App installations first.
    If found, store it and return connected status.
    Otherwise, return the install URL for the user to install the app.
    """
    # Check DB first
    existing = session.query(GithubOrgIntBaseModel).first()
    if existing:
        return GitHubAppConnectionStatus(
            connected=True,
            message="GitHub App is already connected",
            org_name=existing.org_name,
            installation_id=existing.github_install_id,
            install_url=settings.github_app_install_url,
        )

    # Try to auto-discover from GitHub API
    record = _discover_and_store_installation(session)
    if record:
        return GitHubAppConnectionStatus(
            connected=True,
            message="GitHub App is connected (auto-discovered)",
            org_name=record.org_name,
            installation_id=record.github_install_id,
            install_url=settings.github_app_install_url,
        )

    # No installation found - return the install URL
    install_url = settings.github_app_install_url
    if not install_url:
        raise HTTPException(
            status_code=400,
            detail="GITHUB_APP_SLUG is not configured. "
            "Set it to your GitHub App's slug (e.g. 'resourceiq-dev').",
        )

    return GitHubAppConnectResponse(
        install_url=install_url,
        app_slug=settings.GITHUB_APP_SLUG,
    )


@router.get(
    "/auth/callback", dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))]
)
async def github_app_setup_callback(
    session: SessionDep,
    installation_id: int | None = Query(default=None),
    _setup_action: str | None = Query(default=None, alias="setup_action"),
) -> RedirectResponse:
    """
    GitHub App post-installation "Setup URL" callback.
    GitHub redirects here after first install.
    """
    frontend_url = settings.FRONTEND_HOST.rstrip("/")

    if installation_id:
        existing = session.query(GithubOrgIntBaseModel).first()

        if not existing or existing.github_install_id != str(installation_id):
            org_name = "unknown"
            try:
                encoded_jwt = _generate_app_jwt()
                resp = httpx.get(
                    f"https://api.github.com/app/installations/{installation_id}",
                    headers={
                        "Authorization": f"Bearer {encoded_jwt}",
                        "Accept": "application/vnd.github+json",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    org_name = data.get("account", {}).get("login", "unknown")
            except Exception as e:
                logger.error("GitHub callback: %s", e)

            if existing:
                existing.github_install_id = str(installation_id)
                existing.org_name = org_name
            else:
                session.add(
                    GithubOrgIntBaseModel(
                        github_install_id=str(installation_id),
                        org_name=org_name,
                    )
                )
            session.commit()

    return RedirectResponse(
        url=f"{frontend_url}/configuration?github=connected", status_code=302
    )


@router.get(
    "/auth/status",
    response_model=GitHubAppConnectionStatus,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_github_auth_status(session: SessionDep) -> GitHubAppConnectionStatus:
    """
    Return GitHub App connection status.
    Only checks the database - does NOT auto-discover.
    """
    integration = session.query(GithubOrgIntBaseModel).first()

    if not integration:
        return GitHubAppConnectionStatus(
            connected=False,
            message="GitHub App is not connected",
            install_url=settings.github_app_install_url,
        )

    repos_count = None
    try:
        service = GithubIntegrationService(session)
        repos = service.get_repositories()
        repos_count = len(repos)
    except Exception as e:
        logger.warning("Failed to count repos for status: %s", e)

    return GitHubAppConnectionStatus(
        connected=True,
        message="GitHub App is connected",
        org_name=integration.org_name,
        installation_id=integration.github_install_id,
        install_url=settings.github_app_install_url,
        repositories_count=repos_count,
    )


@router.post(
    "/auth/disconnect",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def disconnect_github(session: SessionDep) -> dict[str, str]:
    """Remove the GitHub App installation record from the database."""
    integrations = session.query(GithubOrgIntBaseModel).all()
    for integration in integrations:
        session.delete(integration)
    session.commit()
    return {"message": "GitHub disconnected successfully"}


# ── Repository & Analysis Endpoints ─────────────────────────────


@router.get(
    "/repositories",
    response_model=list[GitHubRepository],
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_repositories(session: SessionDep) -> list[GitHubRepository]:
    """Get all repositories accessible to the GitHub App installation."""
    try:
        service = GithubIntegrationService(session)
        return service.get_repositories()
    except Exception as e:
        logger.error("Failed to fetch repositories: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch repositories: {str(e)}"
        )


@router.get(
    "/org/repos/live",
    response_model=list[GitHubRepository],
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_live_repositories(session: SessionDep) -> list[GitHubRepository]:
    """Get all repositories with live stats (branch and PR counts)."""
    try:
        service = GithubIntegrationService(session)
        return service.get_live_repositories()
    except Exception as e:
        logger.error("Failed to fetch live repositories: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch live repositories: {str(e)}"
        )


@router.get(
    "/repositories/{repo_name}/contributors",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_repo_contributors(
    session: SessionDep,
    repo_name: str,
) -> list[dict[str, Any]]:
    """Get contributors for a specific repository in the org."""
    try:
        service = GithubIntegrationService(session)
        return service.get_repo_contributors(repo_name)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch contributors: {str(e)}"
        )


@router.get(
    "/repositories/{repo_name}/pulls",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_repo_pull_requests(
    session: SessionDep,
    repo_name: str,
    state: str = Query(default="closed", description="PR state: open, closed, all"),
    per_page: int = Query(default=30, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Get pull requests for a specific repository in the org."""
    try:
        service = GithubIntegrationService(session)
        return service.get_repo_pull_requests(
            repo_name, state=state, max_results=per_page
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch pull requests: {str(e)}"
        )


@router.post(
    "/sync",
    response_model=GitHubSyncResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def sync_github(
    session: SessionDep,
    request: GitHubSyncRequest,
) -> GitHubSyncResponse:
    """Trigger a manual sync of GitHub PRs with optional embedding generation."""
    try:
        service = GithubIntegrationService(session)
        return service.sync_repo_prs(
            repo_names=request.repo_names,
            max_prs_per_repo=request.max_prs_per_repo,
            include_open=request.include_open,
            generate_embeddings=request.generate_embeddings,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


# ── Existing GitHub App Endpoints ────────────────────────────────


@router.get(
    "/get_developers", dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))]
)
async def get_developers(session: SessionDep) -> list[GitHubUser]:
    try:
        github_manager = GithubIntegrationService(session)
        return github_manager.get_all_org_members()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/get_closed_prs_context_per_author",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_closed_prs_context_per_author(
    session: SessionDep, author: GitHubUser
) -> list[PullRequestContent]:
    try:
        github_manager = GithubIntegrationService(session)
        return github_manager.get_org_closed_prs_context_by_author(author=author)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/get_closed_prs_context_all_authors",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_closed_prs_context_all_authors(
    session: SessionDep,
) -> dict[str, list[PullRequestContent]]:
    try:
        github_manager = GithubIntegrationService(session)
        return github_manager.get_org_closed_prs_context_all_authors()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
