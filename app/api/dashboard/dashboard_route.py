"""Dashboard API route."""

from fastapi import APIRouter

from app.api.dashboard.dashboard_schema import DashboardResponse
from app.api.dashboard.dashboard_service import get_dashboard_data
from app.utils.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/", response_model=DashboardResponse)
def get_dashboard(session: SessionDep, current_user: CurrentUser) -> DashboardResponse:
    """Get aggregated dashboard metrics."""
    return get_dashboard_data(session)

