"""Dashboard business logic."""

from datetime import datetime, timedelta
from sqlmodel import Session, func, select
from app.api.profiles.profile_model import ResourceProfile
from app.api.user.user_model import User
from app.api.dashboard.dashboard_schema import (
    DashboardResponse,
    TeamMembersCard,
)

def get_dashboard_data(session: Session) -> DashboardResponse:
    """Aggregate all dashboard metrics from the database.""" 

    # ---- 1. Team Members ----
    total_members = session.exec(
        select(func.count()).select_from(User)
    ).one()
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    # NOTE: User model doesn't have created_at yet.
    # If you add it, use: .where(User.created_at >= month_start)
    # For now, set new_this_month = 0 or derive from ResourceProfile.created_at
    new_this_month = session.exec(
        select(func.count()).select_from(ResourceProfile)
        .where(ResourceProfile.created_at >= month_start)
    ).one()

    return DashboardResponse(
        team_members=TeamMembersCard(
            total=total_members,
            new_this_month=new_this_month,
        )
    )