"""Dashboard API route."""

from fastapi import APIRouter

from app.api.dashboard.dashboard_schema import (
    ConnectedIntegrationsCard,
    DashboardResponse,
    GitHubPRStatsCard,
    JiraTaskStatsCard,
    ProfileIntegrationsCard,
    ProfileSkillsCard,
    ProfileWorkloadCard,
)
from app.api.dashboard.dashboard_service import (
    get_dashboard_data,
    get_github_pr_stats,
    get_integration_health,
    get_jira_task_stats,
    get_profile_integrations,
    get_profile_skills,
    get_profile_workload,
)
from app.utils.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/", response_model=DashboardResponse)
def get_dashboard(session: SessionDep, _current_user: CurrentUser) -> DashboardResponse:
    """Get aggregated dashboard metrics."""
    return get_dashboard_data(session)


@router.get("/integrations/health", response_model=ConnectedIntegrationsCard)
def get_integrations_health(
    session: SessionDep, _current_user: CurrentUser
) -> ConnectedIntegrationsCard:
    """Get connected integrations health status."""
    return get_integration_health(session)


@router.get("/github/prs/stats", response_model=GitHubPRStatsCard)
def get_github_stats(
    session: SessionDep, _current_user: CurrentUser
) -> GitHubPRStatsCard:
    """Get GitHub PR statistics for dashboard."""
    return get_github_pr_stats(session)


@router.get("/jira/tasks/stats", response_model=JiraTaskStatsCard)
def get_jira_stats(
    session: SessionDep, _current_user: CurrentUser
) -> JiraTaskStatsCard:
    """Get Jira task statistics for dashboard."""
    return get_jira_task_stats(session)


@router.get("/profiles/skills", response_model=ProfileSkillsCard)
def get_skills_distribution(
    session: SessionDep, _current_user: CurrentUser
) -> ProfileSkillsCard:
    """Get top skills and domains across all team members."""
    return get_profile_skills(session)


@router.get("/profiles/workload", response_model=ProfileWorkloadCard)
def get_workload_analysis(
    session: SessionDep, _current_user: CurrentUser
) -> ProfileWorkloadCard:
    """Get team workload split, overloaded, and idle members."""
    return get_profile_workload(session)


@router.get("/profiles/integrations", response_model=ProfileIntegrationsCard)
def get_integration_adoption(
    session: SessionDep, _current_user: CurrentUser
) -> ProfileIntegrationsCard:
    """Get count of users with connected integrations."""
    return get_profile_integrations(session)
