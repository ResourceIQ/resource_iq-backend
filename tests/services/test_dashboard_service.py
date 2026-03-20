"""Unit tests for dashboard_service module functions.

All database access is mocked — these tests verify aggregation logic,
health-status classification, and workload analysis without a real DB.
"""

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(
    total_workload: int = 0,
    jira_workload: int = 0,
    github_workload: int = 0,
    position: str | None = None,
    skills: str | None = None,
    domains: str | None = None,
    jira_account_id: str | None = None,
    github_id: int | None = None,
    github_login: str | None = None,
    user_id: str | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    p = MagicMock()
    p.total_workload = total_workload
    p.jira_workload = jira_workload
    p.github_workload = github_workload
    if position:
        p.position = MagicMock()
        p.position.name = position
    else:
        p.position = None

    p.skills = skills
    p.domains = domains
    p.jira_account_id = jira_account_id
    p.github_id = github_id
    p.github_login = github_login
    p.user_id = user_id or str(uuid4())
    p.created_at = created_at or datetime(2025, 1, 15)

    p.has_jira = jira_account_id is not None
    p.has_github = github_id is not None or github_login is not None
    p.skills_list = skills.split(",") if skills else []
    p.domains_list = domains.split(",") if domains else []
    return p


# ===================================================================
# 1. Integration health
# ===================================================================

class TestGetIntegrationHealth:
    @patch("app.api.dashboard.dashboard_service.select")
    def test_healthy_when_both_connected_and_valid(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_integration_health

        session = MagicMock()

        jira_token = MagicMock()
        jira_token.expires_at = datetime.utcnow() + timedelta(days=7)
        jira_token.jira_site_url = "https://mysite.atlassian.net"

        github_integration = MagicMock()
        github_integration.org_name = "my-org"

        session.exec.return_value.first.side_effect = [jira_token, github_integration]

        result = get_integration_health(session)

        assert result.jira_connected is True
        assert result.github_connected is True
        assert result.health_status == "Healthy"
        assert result.jira_token_expiring_soon is False

    @patch("app.api.dashboard.dashboard_service.select")
    def test_warning_when_token_expiring_soon(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_integration_health

        session = MagicMock()

        jira_token = MagicMock()
        jira_token.expires_at = datetime.utcnow() + timedelta(hours=2)
        jira_token.jira_site_url = "https://mysite.atlassian.net"

        github_integration = MagicMock()
        github_integration.org_name = "my-org"

        session.exec.return_value.first.side_effect = [jira_token, github_integration]

        result = get_integration_health(session)

        assert result.jira_token_expiring_soon is True
        assert result.health_status == "Warning"
        assert "expiring" in result.health_message.lower()

    @patch("app.api.dashboard.dashboard_service.select")
    def test_warning_when_only_jira_connected(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_integration_health

        session = MagicMock()

        jira_token = MagicMock()
        jira_token.expires_at = datetime.utcnow() + timedelta(days=7)
        jira_token.jira_site_url = "https://mysite.atlassian.net"

        session.exec.return_value.first.side_effect = [jira_token, None]

        result = get_integration_health(session)

        assert result.jira_connected is True
        assert result.github_connected is False
        assert result.health_status == "Warning"
        assert "GitHub not connected" in result.health_message

    @patch("app.api.dashboard.dashboard_service.select")
    def test_warning_when_only_github_connected(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_integration_health

        session = MagicMock()

        github_integration = MagicMock()
        github_integration.org_name = "my-org"

        session.exec.return_value.first.side_effect = [None, github_integration]

        result = get_integration_health(session)

        assert result.jira_connected is False
        assert result.github_connected is True
        assert result.health_status == "Warning"
        assert "Jira not connected" in result.health_message

    @patch("app.api.dashboard.dashboard_service.select")
    def test_disconnected_when_neither_connected(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_integration_health

        session = MagicMock()
        session.exec.return_value.first.side_effect = [None, None]

        result = get_integration_health(session)

        assert result.jira_connected is False
        assert result.github_connected is False
        assert result.health_status == "Disconnected"


# ===================================================================
# 2. Profile skills aggregation
# ===================================================================

class TestGetProfileSkills:
    @patch("app.api.dashboard.dashboard_service.select")
    def test_aggregates_skills_and_domains(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_profile_skills

        session = MagicMock()
        profiles = [
            _make_profile(skills="Python,FastAPI,Docker", domains="Backend,DevOps"),
            _make_profile(skills="Python,React", domains="Backend,Frontend"),
            _make_profile(skills="Docker,Kubernetes", domains="DevOps"),
        ]
        session.exec.return_value.all.return_value = profiles

        result = get_profile_skills(session)

        skill_names = [s.name for s in result.top_skills]
        assert "Python" in skill_names
        assert "Docker" in skill_names

        python_count = next(s.count for s in result.top_skills if s.name == "Python")
        assert python_count == 2

        domain_names = [d.name for d in result.top_domains]
        assert "Backend" in domain_names

    @patch("app.api.dashboard.dashboard_service.select")
    def test_handles_empty_profiles(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_profile_skills

        session = MagicMock()
        session.exec.return_value.all.return_value = []

        result = get_profile_skills(session)

        assert result.top_skills == []
        assert result.top_domains == []

    @patch("app.api.dashboard.dashboard_service.select")
    def test_handles_profiles_without_skills(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_profile_skills

        session = MagicMock()
        profiles = [_make_profile(skills=None, domains=None)]
        session.exec.return_value.all.return_value = profiles

        result = get_profile_skills(session)

        assert result.top_skills == []
        assert result.top_domains == []


# ===================================================================
# 3. Profile integrations count
# ===================================================================

class TestGetProfileIntegrations:
    @patch("app.api.dashboard.dashboard_service.select")
    def test_counts_connected_profiles(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_profile_integrations

        session = MagicMock()
        profiles = [
            _make_profile(jira_account_id="j1", github_id=1),
            _make_profile(jira_account_id="j2", github_id=None),
            _make_profile(jira_account_id=None, github_id=2),
            _make_profile(jira_account_id=None, github_id=None),
        ]
        session.exec.return_value.all.return_value = profiles

        result = get_profile_integrations(session)

        assert result.jira_connected == 2
        assert result.jira_unconnected == 2
        assert result.github_connected == 2
        assert result.github_unconnected == 2

    @patch("app.api.dashboard.dashboard_service.select")
    def test_handles_empty_profiles(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_profile_integrations

        session = MagicMock()
        session.exec.return_value.all.return_value = []

        result = get_profile_integrations(session)

        assert result.jira_connected == 0
        assert result.github_connected == 0


# ===================================================================
# 4. Profile workload analysis
# ===================================================================

class TestGetProfileWorkload:
    @patch("app.api.dashboard.dashboard_service.select")
    def test_identifies_overloaded_and_idle(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_profile_workload

        session = MagicMock()

        user_overloaded = MagicMock()
        user_overloaded.id = uuid4()
        user_overloaded.full_name = "Alice Heavy"
        profile_overloaded = MagicMock()
        profile_overloaded.jira_workload = 10
        profile_overloaded.github_workload = 8
        profile_overloaded.total_workload = 18

        user_idle = MagicMock()
        user_idle.id = uuid4()
        user_idle.full_name = "Bob Idle"
        profile_idle = MagicMock()
        profile_idle.jira_workload = 0
        profile_idle.github_workload = 0
        profile_idle.total_workload = 0

        user_normal = MagicMock()
        user_normal.id = uuid4()
        user_normal.full_name = "Charlie Normal"
        profile_normal = MagicMock()
        profile_normal.jira_workload = 5
        profile_normal.github_workload = 3
        profile_normal.total_workload = 8

        session.exec.return_value.all.return_value = [
            (profile_overloaded, user_overloaded),
            (profile_idle, user_idle),
            (profile_normal, user_normal),
        ]

        result = get_profile_workload(session)

        assert result.jira_vs_github_split["jira"] == 15
        assert result.jira_vs_github_split["github"] == 11
        assert len(result.overloaded_members) == 1
        assert result.overloaded_members[0].name == "Alice Heavy"
        assert len(result.idle_members) == 1
        assert result.idle_members[0].name == "Bob Idle"

    @patch("app.api.dashboard.dashboard_service.select")
    def test_empty_team(self, mock_select: MagicMock) -> None:
        from app.api.dashboard.dashboard_service import get_profile_workload

        session = MagicMock()
        session.exec.return_value.all.return_value = []

        result = get_profile_workload(session)

        assert result.jira_vs_github_split == {"jira": 0, "github": 0}
        assert result.overloaded_members == []
        assert result.idle_members == []


# ===================================================================
# 5. Dashboard data aggregation
# ===================================================================

class TestGetDashboardData:
    def test_aggregates_all_metrics(self) -> None:
        from app.api.dashboard.dashboard_service import get_dashboard_data

        session = MagicMock()

        profiles = [
            _make_profile(total_workload=5, position="Backend"),
            _make_profile(total_workload=0, position="Frontend"),
            _make_profile(total_workload=3, position="Backend"),
        ]

        call_count = 0
        def exec_side_effect(stmt: Any) -> MagicMock:
            nonlocal call_count
            result = MagicMock()
            call_count += 1
            result.one.return_value = {
                1: 10,  # total_members
                2: 8,   # developers
                3: 2,   # admins
                4: 1,   # new_this_month
            }.get(call_count, 5)
            result.all.return_value = profiles
            return result

        session.exec.side_effect = exec_side_effect

        result = get_dashboard_data(session)

        assert result.team_members.total == 10
        assert result.team_members.developers == 8
        assert result.team_members.admins == 2
        assert result.team_utilization.percentage > 0
        assert result.resource_utilization.total_resources == 3
        assert result.resource_utilization.utilized == 2
        assert result.resource_utilization.available == 1

    def test_utilization_high_message(self) -> None:
        from app.api.dashboard.dashboard_service import get_dashboard_data

        session = MagicMock()

        profiles = [_make_profile(total_workload=5) for _ in range(9)]
        profiles.append(_make_profile(total_workload=0))

        call_count = 0
        def exec_side_effect(stmt: Any) -> MagicMock:
            nonlocal call_count
            result = MagicMock()
            call_count += 1
            result.one.return_value = 10
            result.all.return_value = profiles
            return result

        session.exec.side_effect = exec_side_effect

        result = get_dashboard_data(session)

        assert result.team_utilization.percentage == 90.0
        assert result.team_utilization.message == "High utilization"

    def test_utilization_zero_profiles(self) -> None:
        from app.api.dashboard.dashboard_service import get_dashboard_data

        session = MagicMock()

        call_count = 0
        def exec_side_effect(stmt: Any) -> MagicMock:
            nonlocal call_count
            result = MagicMock()
            call_count += 1
            result.one.return_value = 0
            result.all.return_value = []
            return result

        session.exec.side_effect = exec_side_effect

        result = get_dashboard_data(session)

        assert result.team_utilization.percentage == 0.0
        assert result.team_utilization.message == "Capacity available"
        assert result.pending_assignments.count == 0

    def test_resource_allocation_groups_by_position(self) -> None:
        from app.api.dashboard.dashboard_service import get_dashboard_data

        session = MagicMock()

        profiles = [
            _make_profile(position="Backend"),
            _make_profile(position="Backend"),
            _make_profile(position="Frontend"),
            _make_profile(position=None),
        ]

        call_count = 0
        def exec_side_effect(stmt: Any) -> MagicMock:
            nonlocal call_count
            result = MagicMock()
            call_count += 1
            result.one.return_value = 4
            result.all.return_value = profiles
            return result

        session.exec.side_effect = exec_side_effect

        result = get_dashboard_data(session)

        team_names = [a.team_name for a in result.resource_allocation_by_team]
        assert "Backend" in team_names
        assert "Frontend" in team_names
        assert "Unassigned" in team_names

        backend = next(a for a in result.resource_allocation_by_team if a.team_name == "Backend")
        assert backend.headcount == 2
