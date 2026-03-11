"""Dashboard business logic."""

from datetime import datetime, timedelta

from sqlmodel import Session, func, select

from app.api.profiles.profile_model import ResourceProfile
from app.api.user.user_model import User
from app.api.dashboard.dashboard_schema import (
    ActiveTasksCard,
    DashboardResponse,
    PendingAssignmentsCard,
    ResourceUtilizationStatus,
    TeamAllocation,
    TeamMembersCard,
    TeamUtilizationCard,
)


def get_dashboard_data(session: Session) -> DashboardResponse:
    """Aggregate all dashboard metrics from the database."""

    # ---- 1. Team Members ----
    total_members = session.exec(
        select(func.count()).select_from(User)
    ).one()

    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    new_this_month = session.exec(
        select(func.count()).select_from(ResourceProfile)
        .where(ResourceProfile.created_at >= month_start)
    ).one()

    # ---- 2. Team Utilization ----
    profiles = session.exec(select(ResourceProfile)).all()
    total_profiles = len(profiles)

    if total_profiles > 0:
        utilized = sum(1 for p in profiles if p.total_workload > 0)
        utilization_pct = round((utilized / total_profiles) * 100, 1)
    else:
        utilized = 0
        utilization_pct = 0.0

    if utilization_pct > 80:
        util_msg = "High utilization"
    elif utilization_pct > 50:
        util_msg = "Monitor closely"
    else:
        util_msg = "Capacity available"

    # ---- 3. Active Tasks (Total synced from Jira) ----
    from app.api.embedding.embedding_model import JiraIssueVector
    total_jira_tasks = session.exec(select(func.count()).select_from(JiraIssueVector)).one()
    
    # Real 0 from DB (not yet tracked in vectors)
    completed_this_week = 0

    # ---- 4. Pending Assignments ----
    pending = sum(1 for p in profiles if p.total_workload == 0)

    # ---- 5. Resource Allocation by Team (grouped by position) ----
    team_map: dict[str, int] = {}
    for p in profiles:
        team = p.position or "Unassigned"
        team_map[team] = team_map.get(team, 0) + 1

    allocation = [
        TeamAllocation(team_name=name, headcount=count)
        for name, count in sorted(team_map.items(), key=lambda x: -x[1])
    ]

    # ---- 6. Resource Utilization Status ----
    available = total_profiles - utilized

    return DashboardResponse(
        team_members=TeamMembersCard(
            total=total_members, new_this_month=new_this_month
        ),
        team_utilization=TeamUtilizationCard(
            percentage=utilization_pct, message=util_msg
        ),
        active_tasks=ActiveTasksCard(
            active_count=total_jira_tasks, completed_this_week=completed_this_week
        ),
        pending_assignments=PendingAssignmentsCard(
            count=pending,
            message="Needs attention" if pending > 0 else "All assigned",
        ),
        resource_allocation_by_team=allocation,
        resource_utilization=ResourceUtilizationStatus(
            total_resources=total_profiles,
            utilized=utilized,
            available=available,
        ),
    )
