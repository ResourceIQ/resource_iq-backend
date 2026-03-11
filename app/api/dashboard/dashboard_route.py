"""Dashboard API route."""

from fastapi import APIRouter

from app.api.dashboard.dashboard_schema import (
    ConnectedIntegrationsCard, 
    DashboardResponse,
    GitHubPRStatsCard
)
from app.api.dashboard.dashboard_service import (
    get_dashboard_data, 
    get_integration_health,
    get_github_pr_stats
)
from app.utils.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/", response_model=DashboardResponse)
def get_dashboard(session: SessionDep, current_user: CurrentUser) -> DashboardResponse:
    """Get aggregated dashboard metrics."""
    return get_dashboard_data(session)


@router.get("/integrations/health", response_model=ConnectedIntegrationsCard)
def get_integrations_health(session: SessionDep, current_user: CurrentUser) -> ConnectedIntegrationsCard:
    """Get connected integrations health status."""
    return get_integration_health(session)


@router.get("/github/prs/stats", response_model=GitHubPRStatsCard)
def get_github_stats(session: SessionDep, current_user: CurrentUser) -> GitHubPRStatsCard:
    """Get GitHub PR statistics for dashboard."""
    return get_github_pr_stats(session)

