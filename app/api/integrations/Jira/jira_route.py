"""Jira integration API routes."""

from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query

from app.api.integrations.Jira.jira_schema import (
    DeveloperWorkload,
    JiraAuthCallbackResponse,
    JiraAuthConnectResponse,
    JiraIssueContent,
    JiraSyncRequest,
    JiraSyncResponse,
)
from app.api.integrations.Jira.jira_service import JiraIntegrationService
from app.api.profiles.profile_model import ResourceProfile
from app.utils.deps import SessionDep

router = APIRouter(prefix="/jira", tags=["jira"])


@router.get("/auth/connect", response_model=JiraAuthConnectResponse)
async def connect_jira(session: SessionDep) -> JiraAuthConnectResponse:
    """Initiate Atlassian OAuth (3LO) for Jira Cloud."""
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.build_authorization_url()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start OAuth: {str(e)}")


@router.get("/auth/callback", response_model=JiraAuthCallbackResponse)
async def jira_oauth_callback(
    session: SessionDep,
    code: str = Query(..., description="Authorization code from Atlassian"),
    state: str = Query(..., description="State returned by Atlassian"),
) -> JiraAuthCallbackResponse:
    """Handle Atlassian OAuth callback, exchange code, and persist tokens."""
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.handle_oauth_callback(code=code, state=state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}")


@router.get("/projects")
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


@router.get("/users")
async def get_all_jira_users(
    session: SessionDep,
    max_results: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """
    Get all users from Jira Cloud.
    Returns all Atlassian account users (not apps/bots).
    """
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.get_all_jira_users(max_results=max_results)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch Jira users: {str(e)}"
        )


@router.get("/projects/{project_key}/users")
async def get_project_users(
    session: SessionDep,
    project_key: str,
    max_results: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """
    Get all users assignable to issues in a specific Jira project.
    """
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.get_project_users(
            project_key=project_key, max_results=max_results
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch project users: {str(e)}"
        )


@router.get("/users/{account_id}")
async def get_user_by_account_id(
    session: SessionDep,
    account_id: str,
) -> dict[str, Any]:
    """
    Get a specific Jira user by their account ID.
    """
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.get_user_by_account_id(account_id=account_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user: {str(e)}")


@router.post("/sync", response_model=JiraSyncResponse)
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


@router.get("/vectors")
async def get_issue_vectors(
    session: SessionDep,
    project_key: str | None = Query(default=None, description="Filter by project key"),
    assignee_account_id: str | None = Query(
        default=None, description="Filter by assignee"
    ),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """
    Get synced Jira issue vectors from the database.
    Returns vector metadata without the actual embeddings.
    """
    try:
        from typing import cast as type_cast

        from app.api.integrations.Jira.jira_model import JiraIssueVector

        query = session.query(JiraIssueVector)

        if project_key:
            query = query.filter(
                type_cast(Any, JiraIssueVector.project_key == project_key)
            )
        if assignee_account_id:
            query = query.filter(
                type_cast(
                    Any, JiraIssueVector.assignee_account_id == assignee_account_id
                )
            )

        vectors = query.limit(limit).all()

        return [
            {
                "issue_id": v.issue_id,
                "issue_key": v.issue_key,
                "project_key": v.project_key,
                "assignee_account_id": v.assignee_account_id,
                "context": v.context[:500] if v.context else None,  # Truncated context
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "updated_at": v.updated_at.isoformat() if v.updated_at else None,
            }
            for v in vectors
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch issue vectors: {str(e)}"
        )


@router.get("/vectors/{issue_key}")
async def get_issue_vector(session: SessionDep, issue_key: str) -> dict[str, Any]:
    """
    Get a specific Jira issue vector by key.
    """
    try:
        from typing import cast as type_cast

        from app.api.integrations.Jira.jira_model import JiraIssueVector

        vector = (
            session.query(JiraIssueVector)
            .filter(type_cast(Any, JiraIssueVector.issue_key == issue_key))
            .first()
        )

        if not vector:
            raise HTTPException(
                status_code=404, detail=f"Vector for issue {issue_key} not found"
            )

        return {
            "issue_id": vector.issue_id,
            "issue_key": vector.issue_key,
            "project_key": vector.project_key,
            "assignee_account_id": vector.assignee_account_id,
            "context": vector.context,
            "metadata": vector.metadata_json,
            "created_at": vector.created_at.isoformat() if vector.created_at else None,
            "updated_at": vector.updated_at.isoformat() if vector.updated_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch issue vector: {str(e)}"
        )


@router.get("/workload/{jira_account_id}", response_model=DeveloperWorkload)
async def get_workload_by_account(
    session: SessionDep, jira_account_id: str
) -> DeveloperWorkload:
    """
    Calculate and return the Jira workload for a specific user by account ID.
    Useful for the recommendation engine.
    """
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.calculate_developer_workload(jira_account_id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to calculate workload: {str(e)}"
        )


@router.get("/workloads")
async def get_all_workloads(session: SessionDep) -> list[DeveloperWorkload]:
    """
    Calculate and return workloads for all developers with Jira connected.
    Useful for the recommendation engine to find the best-fit developer.
    """
    try:
        jira_service = JiraIntegrationService(session)

        # Get all profiles with Jira accounts connected
        account_col = cast(Any, ResourceProfile.jira_account_id)
        profiles = session.query(ResourceProfile).filter(account_col.isnot(None)).all()

        workloads = []
        for profile in profiles:
            if profile.jira_account_id:
                workload = jira_service.calculate_developer_workload(
                    profile.jira_account_id
                )
                workloads.append(workload)

        # Sort by workload score (ascending - least busy first)
        workloads.sort(key=lambda w: w.workload_score)

        return workloads
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to calculate workloads: {str(e)}"
        )


@router.post("/search/similar")
async def search_similar_issues(
    session: SessionDep,
    query: str,
    n_results: int = Query(default=5, ge=1, le=50),
    project_key: str | None = Query(default=None),
    assignee_account_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """
    Search for similar Jira issues using semantic similarity.
    Useful for finding related issues or suggesting issue assignments.
    Useful for finding related issues or suggesting issue assignments.
    """
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.search_similar_issues(
            query=query,
            n_results=n_results,
            project_key=project_key,
            assignee_account_id=assignee_account_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to search similar issues: {str(e)}"
        )


@router.get("/issues/{issue_key}/context")
async def get_issue_context(session: SessionDep, issue_key: str) -> JiraIssueContent:
    """
    Get full issue context including NLP-ready context string.
    Useful for the recommendation engine.
    """
    try:
        jira_service = JiraIntegrationService(session)
        client = jira_service.get_jira_client()
        issue = client.issue(issue_key)
        return jira_service._parse_issue(issue)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch issue context: {str(e)}"
        )
