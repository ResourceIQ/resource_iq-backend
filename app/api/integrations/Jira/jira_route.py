"""Jira integration API routes."""

from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query

from app.api.integrations.Jira.jira_schema import (
    DeveloperWorkload,
    JiraIssueContent,
    JiraSyncRequest,
    JiraSyncResponse,
    UserMappingRequest,
    UserMappingResponse,
)
from app.api.integrations.Jira.jira_service import JiraIntegrationService
from app.utils.deps import SessionDep

router = APIRouter(prefix="/jira", tags=["jira"])


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


@router.get("/issues")
async def get_issues(
    session: SessionDep,
    project_key: str | None = Query(default=None, description="Filter by project key"),
    status: str | None = Query(default=None, description="Filter by status"),
    assignee_account_id: str | None = Query(
        default=None, description="Filter by assignee"
    ),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """
    Get synced Jira issues from the database.
    """
    try:
        from typing import cast as type_cast

        from app.api.integrations.Jira.jira_model import JiraIssue

        query = session.query(JiraIssue)

        if project_key:
            query = query.filter(type_cast(Any, JiraIssue.project_key == project_key))
        if status:
            query = query.filter(type_cast(Any, JiraIssue.status == status))
        if assignee_account_id:
            query = query.filter(
                type_cast(Any, JiraIssue.assignee_account_id == assignee_account_id)
            )

        issues = query.limit(limit).all()

        return [
            {
                "issue_id": i.issue_id,
                "issue_key": i.issue_key,
                "project_key": i.project_key,
                "summary": i.summary,
                "description": i.description,
                "issue_type": i.issue_type,
                "status": i.status,
                "priority": i.priority,
                "labels": i.labels.split(",") if i.labels else [],
                "assignee": {
                    "account_id": i.assignee_account_id,
                    "display_name": i.assignee_display_name,
                    "email": i.assignee_email,
                }
                if i.assignee_account_id
                else None,
                "issue_url": i.issue_url,
                "jira_created_at": i.jira_created_at.isoformat()
                if i.jira_created_at
                else None,
                "jira_updated_at": i.jira_updated_at.isoformat()
                if i.jira_updated_at
                else None,
            }
            for i in issues
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch issues: {str(e)}")


@router.get("/issues/{issue_key}")
async def get_issue(session: SessionDep, issue_key: str) -> dict[str, Any]:
    """
    Get a specific Jira issue by key.
    """
    try:
        from typing import cast as type_cast

        from app.api.integrations.Jira.jira_model import JiraIssue

        issue = (
            session.query(JiraIssue)
            .filter(type_cast(Any, JiraIssue.issue_key == issue_key))
            .first()
        )

        if not issue:
            raise HTTPException(status_code=404, detail=f"Issue {issue_key} not found")

        return {
            "issue_id": issue.issue_id,
            "issue_key": issue.issue_key,
            "project_key": issue.project_key,
            "summary": issue.summary,
            "description": issue.description,
            "issue_type": issue.issue_type,
            "status": issue.status,
            "priority": issue.priority,
            "labels": issue.labels.split(",") if issue.labels else [],
            "assignee": {
                "account_id": issue.assignee_account_id,
                "display_name": issue.assignee_display_name,
                "email": issue.assignee_email,
            }
            if issue.assignee_account_id
            else None,
            "reporter": {
                "account_id": issue.reporter_account_id,
                "display_name": issue.reporter_display_name,
            }
            if issue.reporter_account_id
            else None,
            "issue_url": issue.issue_url,
            "comments": issue.comments_json,
            "jira_created_at": issue.jira_created_at.isoformat()
            if issue.jira_created_at
            else None,
            "jira_updated_at": issue.jira_updated_at.isoformat()
            if issue.jira_updated_at
            else None,
            "jira_resolved_at": issue.jira_resolved_at.isoformat()
            if issue.jira_resolved_at
            else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch issue: {str(e)}")


@router.get("/developers")
async def get_developers(session: SessionDep) -> list[dict[str, Any]]:
    """
    Get all developers/users who have been assigned Jira issues.
    """
    try:
        jira_service = JiraIntegrationService(session)
        return jira_service.get_all_developers()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch developers: {str(e)}"
        )


@router.get("/developers/{jira_account_id}/workload", response_model=DeveloperWorkload)
async def get_developer_workload(
    session: SessionDep, jira_account_id: str
) -> DeveloperWorkload:
    """
    Calculate and return the workload for a specific developer.
    Satisfies FR8: Workload calculation based on open/in-progress tickets.
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
    Calculate and return workloads for all developers.
    Useful for the recommendation engine to find the best-fit developer.
    """
    try:
        from app.api.integrations.Jira.jira_model import DeveloperProfile

        jira_service = JiraIntegrationService(session)

        # Get all developers with Jira accounts - cast column for mypy
        account_col = cast(Any, DeveloperProfile.jira_account_id)
        profiles = session.query(DeveloperProfile).filter(account_col.isnot(None)).all()

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


@router.post("/users/map", response_model=UserMappingResponse)
async def map_user(
    session: SessionDep, request: UserMappingRequest
) -> UserMappingResponse:
    """
    Map a Jira user to internal ResourceIQ profile and/or GitHub account.
    Satisfies UC-002: Handle User Mapping.
    """
    try:
        jira_service = JiraIntegrationService(session)
        profile = jira_service.map_user(
            jira_account_id=request.jira_account_id,
            internal_user_id=request.internal_user_id,
            github_login=request.github_login,
        )

        return UserMappingResponse(
            jira_account_id=profile.jira_account_id or "",
            jira_display_name=profile.jira_display_name,
            jira_email=profile.jira_email,
            github_login=profile.github_login,
            github_id=profile.github_id,
            internal_user_id=profile.internal_user_id,
            mapped=bool(profile.internal_user_id or profile.github_login),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to map user: {str(e)}")


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
    Prepares data for NLP recommendation engine (FR5).
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
    Useful for the recommendation engine (FR5).
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
