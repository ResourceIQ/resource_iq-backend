"""Jira integration API routes."""

import urllib.parse
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query,Depends
from fastapi.responses import RedirectResponse

from app.api.integrations.Jira.jira_model import JiraOAuthToken
from app.api.integrations.Jira.jira_schema import (
    JiraAssignIssueRequest,
    JiraAssignIssueResponse,
    JiraAuthConnectResponse,
    JiraCreateIssueRequest,
    JiraCreateIssueResponse,
    JiraIssueDetailResponse,
    JiraIssueTypeStatusResponse,
    JiraIssueTypeStatusUpdateRequest,
    JiraLiveStatsResponse,
    JiraSyncRequest,
    JiraSyncResponse,
)
from app.api.integrations.Jira.jira_service import JiraIntegrationService
from app.core.config import settings
from app.utils.deps import SessionDep,RoleChecker
from app.api.user.user_model import Role

router = APIRouter(prefix="/jira", tags=["jira"])


@router.get("/auth/connect", response_model=JiraAuthConnectResponse,dependencies=[Depends(RoleChecker([Role.ADMIN,Role.MODERATOR]))])
async def connect_jira(session: SessionDep) -> JiraAuthConnectResponse:
    """Initiate Atlassian OAuth (3LO) for Jira Cloud."""
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.build_authorization_url()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start OAuth: {str(e)}")


@router.get("/auth/callback",dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
async def jira_oauth_callback(
    session: SessionDep,
    code: str = Query(..., description="Authorization code from Atlassian"),
    state: str = Query(..., description="State returned by Atlassian"),
) -> RedirectResponse:
    """Handle Atlassian OAuth callback, exchange code, and redirect to frontend."""
    frontend_url = settings.FRONTEND_HOST.rstrip("/")

    try:
        jira_service = JiraIntegrationService(session)
        result = jira_service.handle_oauth_callback(code=code, state=state)

        # Build success redirect URL with connection details
        params = {"jira": "connected"}
        if result.cloud_id:
            params["cloud_id"] = result.cloud_id

        redirect_url = f"{frontend_url}/configuration?{urllib.parse.urlencode(params)}"
        return RedirectResponse(url=redirect_url, status_code=302)

    except ValueError as e:
        # Redirect to frontend with error message
        error_message = urllib.parse.quote(str(e))
        redirect_url = f"{frontend_url}/configuration?jira=error&error={error_message}"
        return RedirectResponse(url=redirect_url, status_code=302)

    except Exception as e:
        # Redirect to frontend with generic error
        error_message = urllib.parse.quote(f"OAuth callback failed: {str(e)}")
        redirect_url = f"{frontend_url}/configuration?jira=error&error={error_message}"
        return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/auth/status",dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
async def get_jira_auth_status(session: SessionDep) -> dict[str, Any]:
    """Return Jira OAuth connection status for the configuration page."""
    token = (
        session.query(JiraOAuthToken)
        .order_by(cast(Any, JiraOAuthToken.expires_at).desc())
        .first()
    )

    if not token:
        return {
            "connected": False,
            "message": "Jira is not connected",
            "cloud_id": None,
            "jira_site_url": None,
            "atlassian_account_id": None,
            "expires_at": None,
            "is_expired": False,
            "can_refresh": False,
            "scope": None,
            "user_id": None,
        }

    is_expired = token.expires_at <= datetime.utcnow()
    can_refresh = bool(token.refresh_token)
    message = (
        "Jira token is connected but expired" if is_expired else "Jira is connected"
    )

    return {
        "connected": True,
        "message": message,
        "cloud_id": token.cloud_id,
        "jira_site_url": token.jira_site_url,
        "atlassian_account_id": None,
        "expires_at": token.expires_at,
        "is_expired": is_expired,
        "can_refresh": can_refresh,
        "scope": token.scope,
        "user_id": None,
    }


@router.post("/auth/disconnect",dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
async def disconnect_jira_auth(session: SessionDep) -> dict[str, str]:
    """Disconnect Jira OAuth by removing stored tokens."""
    tokens = session.query(JiraOAuthToken).all()
    for token in tokens:
        session.delete(token)
    session.commit()
    return {"message": "Jira disconnected successfully"}


@router.post(
    "/issue-type-statuses/sync",
    response_model=list[JiraIssueTypeStatusResponse],dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))]
)
async def sync_issue_type_statuses(
    session: SessionDep,
) -> list[JiraIssueTypeStatusResponse]:
    """Fetch issue types and their workflow statuses from Jira.
    User-configured status selections are preserved across re-syncs."""
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.sync_issue_type_statuses()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync issue types: {str(e)}",
        )


@router.get(
    "/issue-type-statuses",
    response_model=list[JiraIssueTypeStatusResponse],dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))]
)
async def get_issue_type_statuses(
    session: SessionDep,
) -> list[JiraIssueTypeStatusResponse]:
    """Return all issue types with their available and selected statuses."""
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.get_issue_type_statuses()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch issue type statuses: {str(e)}",
        )


@router.put(
    "/issue-type-statuses/{issue_type_id}",
    response_model=JiraIssueTypeStatusResponse,dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))]
)
async def update_issue_type_selected_statuses(
    session: SessionDep,
    issue_type_id: str,
    body: JiraIssueTypeStatusUpdateRequest,
) -> JiraIssueTypeStatusResponse:
    """Update which statuses qualify for embedding on an issue type."""
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.update_issue_type_selected_statuses(
            issue_type_id=issue_type_id,
            selected_statuses=body.selected_statuses,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update issue type statuses: {str(e)}",
        )


@router.get("/projects",dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
async def get_projects(session: SessionDep) -> list[dict[str, Any]]:
    """
    Get all accessible Jira projects.
    """
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.get_all_projects()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch projects: {str(e)}"
        )


@router.get("/issue-types",dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
async def get_issue_types(session: SessionDep) -> list[dict[str, Any]]:
    """Get all available Jira issue types (excludes subtasks)."""
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.fetch_issue_types()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch issue types: {str(e)}"
        )


@router.get("/issues/{issue_key}", response_model=JiraIssueDetailResponse,dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
async def get_issue(
    session: SessionDep,
    issue_key: str,
) -> JiraIssueDetailResponse:
    """Fetch a single Jira issue by its key."""
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.get_issue(issue_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch issue: {str(e)}")


@router.post("/issues", response_model=JiraCreateIssueResponse,dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
async def create_issue(
    session: SessionDep,
    request: JiraCreateIssueRequest,
) -> JiraCreateIssueResponse:
    """Create a Jira issue with optional assignee.

    When ``assignee_user_id`` is provided the corresponding
    ``jira_account_id`` is resolved from the resource profile and the
    issue is assigned automatically.
    """
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.create_issue(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create issue: {str(e)}")


@router.put("/issues/{issue_key}/assignee", response_model=JiraAssignIssueResponse,dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
async def assign_issue(
    session: SessionDep,
    issue_key: str,
    request: JiraAssignIssueRequest,
) -> JiraAssignIssueResponse:
    """Assign or reassign a Jira issue to a ResourceIQ user."""
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.assign_issue(issue_key, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to assign issue: {str(e)}")


@router.post("/sync", response_model=JiraSyncResponse,dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
async def sync_issues(
    session: SessionDep,
    request: JiraSyncRequest,
) -> JiraSyncResponse:
    """
    Trigger a manual sync of Jira issues.
    This endpoint satisfies the requirement for Workplace Administrators
    to initiate a manual sync (POST /api/v1/jira/sync).
    """
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.sync_issues(
            project_keys=request.project_keys,
            max_results=request.max_results,
            include_closed=request.include_closed,
            sync_comments=request.sync_comments,
            generate_embeddings=request.generate_embeddings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/live/stats", response_model=JiraLiveStatsResponse,dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
async def get_jira_live_stats(
    session: SessionDep,
    project_keys: list[str] | None = Query(
        default=None, description="Optional project keys to filter stats"
    ),
) -> JiraLiveStatsResponse:
    """Fetch real-time task statistics directly from Jira across projects."""
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.get_live_task_stats(project_keys=project_keys)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch live Jira stats: {str(e)}"
        )
