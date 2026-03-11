"""Dashboard business logic."""

from datetime import datetime, timedelta

from sqlmodel import Session, func, select

from app.api.profiles.profile_model import ResourceProfile
from app.api.user.user_model import User
from app.api.dashboard.dashboard_schema import (
    ActiveTasksCard,
    AssigneeTaskCount,
    ConnectedIntegrationsCard,
    ContributorPRCount,
    DashboardResponse,
    DomainCount,
    GitHubPRStatsCard,
    JiraTaskStatsCard,
    PendingAssignmentsCard,
    ProfileIntegrationsCard,
    ProfileSkillsCard,
    ProfileWorkloadCard,
    ProjectTaskCount,
    RepoPRCount,
    ResourceUtilizationStatus,
    SkillCount,
    TeamAllocation,
    TeamMembersCard,
    TeamUtilizationCard,
    UserWorkload,
)


def get_integration_health(session: Session) -> ConnectedIntegrationsCard:
    """Check Jira OAuth token and GitHub org integration status."""
    from app.api.integrations.Jira.jira_model import JiraOAuthToken
    from app.api.integrations.GitHub.github_model import GithubOrgIntBaseModel

    # --- Jira ---
    jira_token = session.exec(
        select(JiraOAuthToken).order_by(JiraOAuthToken.updated_at.desc())  # type: ignore[union-attr]
    ).first()

    jira_connected = jira_token is not None
    jira_token_expires_at = jira_token.expires_at if jira_token else None
    jira_site_url = jira_token.jira_site_url if jira_token else None

    # Token expiring within 24 hours?
    if jira_token and jira_token.expires_at:
        jira_token_expiring_soon = jira_token.expires_at <= datetime.utcnow() + timedelta(hours=24)
    else:
        jira_token_expiring_soon = False

    # --- GitHub ---
    github_integration = session.exec(select(GithubOrgIntBaseModel)).first()
    github_connected = github_integration is not None
    github_org_name = github_integration.org_name if github_integration else None

    # --- Overall Health ---
    if jira_connected and github_connected and not jira_token_expiring_soon:
        health_status = "Healthy"
        health_message = "All integrations connected and tokens valid"
    elif jira_token_expiring_soon:
        health_status = "Warning"
        health_message = "Jira token expiring soon — refresh recommended"
    elif jira_connected or github_connected:
        parts = []
        if not jira_connected:
            parts.append("Jira not connected")
        if not github_connected:
            parts.append("GitHub not connected")
        health_status = "Warning"
        health_message = "; ".join(parts)
    else:
        health_status = "Disconnected"
        health_message = "No integrations connected"

    return ConnectedIntegrationsCard(
        jira_connected=jira_connected,
        github_connected=github_connected,
        jira_token_expires_at=jira_token_expires_at,
        jira_token_expiring_soon=jira_token_expiring_soon,
        jira_site_url=jira_site_url,
        github_org_name=github_org_name,
        health_status=health_status,
        health_message=health_message,
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


def get_github_pr_stats(session: Session) -> GitHubPRStatsCard:
    """Get aggregated GitHub PR statistics."""
    from app.api.embedding.embedding_model import GitHubPRVector

    # Total Active PRs
    total_prs = session.exec(select(func.count()).select_from(GitHubPRVector)).one()

    # PRs by Repository
    repo_counts = session.exec(
        select(GitHubPRVector.repo_name, func.count(GitHubPRVector.id))
        .group_by(GitHubPRVector.repo_name)
        .order_by(func.count(GitHubPRVector.id).desc())
    ).all()
    prs_by_repo = [RepoPRCount(repo_name=row[0], count=row[1]) for row in repo_counts]

    # Top Contributors
    contributor_counts = session.exec(
        select(GitHubPRVector.author_login, func.count(GitHubPRVector.id))
        .group_by(GitHubPRVector.author_login)
        .order_by(func.count(GitHubPRVector.id).desc())
        .limit(5)
    ).all()
    top_contributors = [
        ContributorPRCount(author_login=row[0], count=row[1])
        for row in contributor_counts
    ]

    return GitHubPRStatsCard(
        total_active_prs=total_prs,
        prs_by_repo=prs_by_repo,
        top_contributors=top_contributors,
    )


def get_jira_task_stats(session: Session) -> JiraTaskStatsCard:
    """Get aggregated Jira task statistics."""
    from app.api.embedding.embedding_model import JiraIssueVector

    # Total Active Tasks
    total_tasks = session.exec(select(func.count()).select_from(JiraIssueVector)).one()

    # Unassigned Tasks
    unassigned_count = session.exec(
        select(func.count()).select_from(JiraIssueVector).where(JiraIssueVector.assignee_account_id == None)
    ).one()

    # Tasks by Project
    project_counts = session.exec(
        select(JiraIssueVector.project_key, func.count(JiraIssueVector.id))
        .group_by(JiraIssueVector.project_key)
        .order_by(func.count(JiraIssueVector.id).desc())
    ).all()
    tasks_by_project = [ProjectTaskCount(project_key=row[0], count=row[1]) for row in project_counts]

    # Top Assignees
    assignee_counts = session.exec(
        select(JiraIssueVector.assignee_account_id, func.count(JiraIssueVector.id))
        .where(JiraIssueVector.assignee_account_id != None)
        .group_by(JiraIssueVector.assignee_account_id)
        .order_by(func.count(JiraIssueVector.id).desc())
        .limit(5)
    ).all()
    top_assignees = [
        AssigneeTaskCount(assignee_account_id=row[0], count=row[1])
        for row in assignee_counts
    ]

    return JiraTaskStatsCard(
        total_active_tasks=total_tasks,
        unassigned_tasks=unassigned_count,
        tasks_by_project=tasks_by_project,
        top_assignees=top_assignees,
    )


def get_profile_skills(session: Session) -> ProfileSkillsCard:
    """Aggregate skills and domains from all resource profiles."""
    profiles = session.exec(select(ResourceProfile)).all()

    skill_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}

    for profile in profiles:
        for skill in profile.skills_list:
            skill_clean = skill.strip()
            if skill_clean:
                skill_counts[skill_clean] = skill_counts.get(skill_clean, 0) + 1

        for domain in profile.domains_list:
            domain_clean = domain.strip()
            if domain_clean:
                domain_counts[domain_clean] = domain_counts.get(domain_clean, 0) + 1

    top_skills = [
        SkillCount(name=k, count=v)
        for k, v in sorted(skill_counts.items(), key=lambda item: -item[1])[:10]
    ]

    top_domains = [
        DomainCount(name=k, count=v)
        for k, v in sorted(domain_counts.items(), key=lambda item: -item[1])[:10]
    ]

    return ProfileSkillsCard(top_skills=top_skills, top_domains=top_domains)


def get_profile_workload(session: Session) -> ProfileWorkloadCard:
    """Analyze team workload capacity and distribution."""
    # We join with User to get the actual names
    statement = select(ResourceProfile, User).join(User)
    results = session.exec(statement).all()

    total_jira = 0
    total_github = 0
    overloaded = []
    idle = []

    WORKLOAD_THRESHOLD = 15

    for profile, user in results:
        total_jira += profile.jira_workload
        total_github += profile.github_workload

        user_data = UserWorkload(
            user_id=str(user.id),
            name=user.full_name,
            jira_workload=profile.jira_workload,
            github_workload=profile.github_workload,
            total_workload=profile.total_workload,
        )

        if profile.total_workload >= WORKLOAD_THRESHOLD:
            overloaded.append(user_data)
        elif profile.total_workload == 0:
            idle.append(user_data)

    # Sort the lists
    overloaded.sort(key=lambda x: -x.total_workload)
    idle.sort(key=lambda x: user.full_name or "")

    return ProfileWorkloadCard(
        jira_vs_github_split={"jira": total_jira, "github": total_github},
        overloaded_members=overloaded,
        idle_members=idle,
    )


def get_profile_integrations(session: Session) -> ProfileIntegrationsCard:
    """Count how many users have connected Jira/GitHub accounts."""
    profiles = session.exec(select(ResourceProfile)).all()
    
    jira_connected = sum(1 for p in profiles if p.has_jira)
    github_connected = sum(1 for p in profiles if p.has_github)
    
    total = len(profiles)

    return ProfileIntegrationsCard(
        jira_connected=jira_connected,
        jira_unconnected=total - jira_connected,
        github_connected=github_connected,
        github_unconnected=total - github_connected,
    )
